"""Plan selection at the authors' extraction and syntactic-check sites."""
import ast
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from functools import partial

DECODER = json.JSONDecoder()
BRACED = re.compile(r"{.*}", re.DOTALL)
OPEN_BRACE = re.compile(r"{")
COORD = r"(\d+(?:\.\d+)?)"
COORD_PAIR = rf"\[\s*{COORD}\s*,\s*{COORD}\s*\]"
PLAN_AGENT = re.compile("Agent" + COORD_PAIR)
STEP_KEY = re.compile(r"(?:step\s+)?(0*[1-9][0-9]*)", re.IGNORECASE)
@dataclass(frozen=True)
class MoveSyntax:
    place: str
    strict: re.Pattern
    spaced: re.Pattern


def move_syntax(place, sites):
    strict = re.compile(r"move\((box_\w+),\s(?:(" + sites + ")|" + place + COORD_PAIR + r")\)")
    spaced = re.compile(r"move\s*\(\s*(box_\w+)\s*,\s*(?:(" + sites + ")|" + place + r"\s*"
                        + COORD_PAIR + r")\s*\)")
    return MoveSyntax(place, strict, spaced)


SQUARE_MOVES = move_syntax("square", r"target_\w+|dropoff(?:_\w+)?")
CORNER_MOVES = move_syntax("position", r"target_\w+")
OWN_MOVE, SPACED_MOVE = SQUARE_MOVES.strict, SQUARE_MOVES.spaced
OWN_FORMS = ("list", "nested", "self_dict", "string", "fenced")
JSON_NULL = re.compile(r"\bnull\b")
UNUSABLE = object()


@dataclass(frozen=True)
class ReplyShape:
    """Reader provenance for matched call records and offline replay."""
    form: str | None
    accepted: bool
    reason: str | None = None
    detail: str | None = None


def unique_keys(pairs):
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise ValueError("Repeated key in OWN reply")
    return obj


OWN_DECODER = json.JSONDecoder(object_pairs_hook=unique_keys)


def python_own_value(node):
    # Read literal data only. An unknown expression is an unusable entry, never an action.
    if isinstance(node, ast.List):
        return [python_own_value(item) for item in node.elts]
    if isinstance(node, ast.Dict):
        if not all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in node.keys):
            raise ValueError("Expected string keys")
        return unique_keys([(k.value, python_own_value(v)) for k, v in zip(node.keys, node.values)])
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id == "null":
        return None
    return UNUSABLE


def decode_own_value(text):
    try:
        return OWN_DECODER.decode(text), False
    except json.JSONDecodeError:
        if not text.startswith(("[", "{")):
            raise
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError as exc:
        raise ValueError("Invalid OWN literal") from exc
    if not isinstance(node, (ast.List, ast.Dict)):
        raise ValueError("Expected an OWN list or object")
    return python_own_value(node), True


def own_prefix(text, *, keep_tail=False):
    """Split a damaged outer list at its own commas, preserving the first broken slot."""
    if not text.startswith("["):
        return None
    fields = []
    start, depth, quote, escaped = 1, 0, "", False
    for i in range(start, len(text)):
        char = text[i]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            if not depth:
                if char != "]" or text[i + 1:].strip():
                    return None
                if text[start:i].strip():
                    fields.append(text[start:i])
                break
            depth -= 1
        elif char == "," and not depth:
            fields.append(text[start:i])
            start = i + 1
    else:
        fields.append("")  # The final entry never closed.
    entries = []
    for field in fields:
        # The enclosing list supports both Python-quoted and JSON entries.
        try:
            item, _ = decode_own_value("[" + field + "]")
        except (ValueError, RecursionError):
            item = []
        entry = item[0] if len(item) == 1 else UNUSABLE
        if entry is UNUSABLE and not keep_tail:
            return entries + [UNUSABLE] * (len(fields) - len(entries)) if entries else None
        entries.append(entry)
    if keep_tail and UNUSABLE in entries:
        return entries
    return None


def embedded_fragments(text, *, own=False, prior_shapes=False, cut=False):
    """Yield top-level text and whether the value reached its closing delimiter."""
    start, depth, quote, escaped = 0, 0, "", False
    scalar_end = 0
    for i, char in enumerate(text):
        if i < scalar_end:
            continue
        if not depth:
            if char in "[{":
                start, depth = i, 1
            elif own and (char == '"' or (char == "n" and JSON_NULL.match(text, i))):
                try:
                    _, scalar_end = OWN_DECODER.raw_decode(text, i)
                except (ValueError, RecursionError):
                    if cut and char == '"':
                        yield text[i:], False
                        return
                    continue
                yield text[i:scalar_end], True
        elif quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char == '"' or (own and not prior_shapes and char == "'"):
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if not depth:
                yield text[start:i + 1], True
    if depth:
        yield text[start:], False


def embedded_values(text, *, own=False, prior_shapes=False, decoder=DECODER, keep_tail=False):
    """Scan complete top-level values without selecting members of a rejected container."""
    for fragment, closed in embedded_fragments(text, own=own, prior_shapes=prior_shapes):
        if not closed:
            continue
        try:
            if own and not prior_shapes:
                yield decode_own_value(fragment)[0]
            else:
                yield (OWN_DECODER if own else decoder).decode(fragment)
        except (ValueError, RecursionError):
            if own and not prior_shapes:
                prefix = own_prefix(fragment, keep_tail=keep_tail)
                if prefix is not None:
                    yield prefix


def own_entry(value, syntax=SQUARE_MOVES):
    return value is None or (isinstance(value, str) and syntax.strict.fullmatch(value) is not None)


def speaker_coordinates(name):
    match = PLAN_AGENT.fullmatch(name) if isinstance(name, str) else None
    return tuple(map(Decimal, match.groups())) if match else None


def foreign_agent(value, allowed):
    """Check the whole candidate before selecting a wrapper or retaining a prefix."""
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for name, nested in current.items():
                position = speaker_coordinates(name)
                if position is not None and position not in allowed:
                    return name
                stack.append(nested)
        elif isinstance(current, list):
            stack.extend(reversed(current))
    return None


def as_sequence(value, horizon, own, lenient, *, agent_positions=None, format_errors=None, prior_shapes=False, syntax=SQUARE_MOVES):
    if not own and lenient and isinstance(value, dict):
        steps = [] if prior_shapes else [STEP_KEY.fullmatch(k.strip()) for k in value]
        if steps and all(steps):
            numbered = {Decimal(m[1]): plan for m, plan in zip(steps, value.values())}
            if len(numbered) != len(value):
                if format_errors is not None:
                    format_errors.append("Each step number must appear only once.")
                return None
            value = [numbered[n] for n in sorted(numbered)]
        elif len(value) == 1 and isinstance(next(iter(value.values())), list):
            value = next(iter(value.values()))
        elif prior_shapes and any(isinstance(v, list) for v in value.values()):
            return None
        else:
            value = [value]
    if not isinstance(value, list) or len(value) > horizon:
        return None
    if own:
        if len(value) != horizon or not all(own_entry(v, syntax) for v in value):
            return None
    else:
        for plan in value:
            if not isinstance(plan, dict):
                return None
            if prior_shapes:
                continue
            for key in plan:
                position = speaker_coordinates(key)
                if position is None or (agent_positions is not None and position not in agent_positions):
                    if format_errors is not None:
                        format_errors.append(f"{json.dumps(key)} is not an agent name on this board. "
                                             "Use an Agent[row, col] key from the current state in each joint plan.")
                    return None
    return value


@dataclass(frozen=True)
class OwnReply:
    entries: list
    form: str
    padded: bool = False
    cut: bool = False
    invalid_position: int | None = None
    normalized: bool = False

    @property
    def rescued(self):
        return self.form != "list" or self.padded or self.cut or self.normalized or self.invalid_position is not None


def normalize_own_entry(value, speaker=None, diagnostic=None, *, matched_shapes=False, syntax=SQUARE_MOVES):
    if isinstance(value, dict):
        if not value:
            return None if matched_shapes else UNUSABLE
        if len(value) != 1:
            return UNUSABLE
        (name, value), = value.items()
        if name == "action":
            # Pre-matched lenient spelling retained for legacy callers.
            pass
        elif not matched_shapes:
            return UNUSABLE
        elif speaker_coordinates(name) != speaker_coordinates(speaker or ""):
            if diagnostic is not None:
                diagnostic.update(reason="foreign_agent", detail=str(name))
            return UNUSABLE
        if matched_shapes and value == {}:
            return None
    if own_entry(value, syntax):
        return value
    if not isinstance(value, str):
        return UNUSABLE
    text = value.strip()
    if text.lower() in ("", "null", "none", "wait") or (matched_shapes and text.lower() in ("idle", "{}")):
        return None
    match = syntax.spaced.fullmatch(text)
    if match is None:
        return UNUSABLE
    box, site, row, col = match.groups()
    if row is not None:
        site = f"{syntax.place}[{row}, {col}]"
    return f"move({box}, {site})"


def own_value(value, horizon, speaker, *, embedded=False, normalized=False, prior_shapes=False, diagnostic=None,
              matched_shapes=False, pad_to_horizon=True, syntax=SQUARE_MOVES):
    form = "fenced" if embedded else "list"
    if isinstance(value, dict):
        if not matched_shapes:
            if len(value) != 1:
                return None
            (name, value), = value.items()
            if speaker_coordinates(name) != speaker_coordinates(speaker or "") or not isinstance(value, list):
                return None
            form = "self_dict"
        elif not value:
            if horizon != 1 and diagnostic is not None:
                diagnostic.update(reason="wrong_length", detail=f"expected {horizon}, got 1")
            return OwnReply([None], "wait_object") if horizon == 1 else None
        # Historical lenient OWN replies used {self: [entries]}; retain that
        # spelling outside strict mode while accepting the new entry objects.
        if matched_shapes and len(value) == 1:
            (name, wrapped), = value.items()
            if speaker_coordinates(name) == speaker_coordinates(speaker or "") and isinstance(wrapped, list):
                value, form = wrapped, "self_dict"
            else:
                entry = normalize_own_entry(value, speaker, diagnostic, matched_shapes=matched_shapes, syntax=syntax)
                if horizon != 1:
                    if diagnostic is not None:
                        diagnostic.setdefault("reason", "wrong_length")
                        diagnostic.setdefault("detail", f"expected {horizon}, got 1")
                    return None
                if entry is UNUSABLE:
                    return None
                return OwnReply([entry], "wait_object" if not value else "self_object_h1", normalized=normalized)
        elif matched_shapes:
            return None
    elif not isinstance(value, list):
        if prior_shapes:
            return OwnReply([value], "string") if horizon == 1 and own_entry(value, syntax) else None
        entry = normalize_own_entry(value, speaker, diagnostic, matched_shapes=matched_shapes, syntax=syntax)
        if entry is None:
            length = horizon if pad_to_horizon else 1
            return OwnReply([None] * length, "string", padded=length > 1)
        if horizon != 1 and entry is not UNUSABLE:
            if diagnostic is not None:
                diagnostic.setdefault("reason", "not_list")
            return None
        return OwnReply([entry], "string") if horizon == 1 and entry is not UNUSABLE else None

    if value and isinstance(value[0], list):
        if len(value) == 1:
            value = value[0]
        else:
            value = [entry[0] if isinstance(entry, list) and len(entry) == 1 else UNUSABLE for entry in value]
        if form != "self_dict":
            form = "nested"
    if prior_shapes and not all(own_entry(entry, syntax) for entry in value):
        return None
    size = len(value)
    object_entries = any(isinstance(raw, dict) for raw in value)
    entries = []
    invalid_position = None
    for position, raw in enumerate(value, 1):
        entry = normalize_own_entry(raw, speaker, diagnostic, matched_shapes=matched_shapes, syntax=syntax)
        if entry is UNUSABLE:
            if matched_shapes and diagnostic is not None and diagnostic.get("reason") == "foreign_agent":
                return None
            if not 1 < position <= horizon:
                return None
            invalid_position = position
            break
        normalized |= entry != raw
        if position <= horizon:
            entries.append(entry)
    if pad_to_horizon:
        entries.extend([None] * (horizon - len(entries)))
    if matched_shapes and object_entries and form in ("list", "fenced"):
        if all(raw == {} for raw in value):
            form = "empty_object_list"
        else:
            form = "self_object_list" if all(isinstance(raw, dict) for raw in value) else "mixed_list"
        if embedded:
            form = "fenced_" + form
    return OwnReply(entries, form, padded=pad_to_horizon and size < horizon, cut=size > horizon,
                    invalid_position=invalid_position, normalized=normalized)


def read_own_reply(reply, horizon, speaker, mode, *, prior_shapes=False, matched_shapes=False, pad_to_horizon=True, syntax=SQUARE_MOVES):
    """Return an OWN parse plus a stable accepted/refusal shape record."""
    diagnostic = {}

    def result(parsed):
        if parsed is None:
            return None, ReplyShape(None, False, diagnostic.get("reason", "unreadable"), diagnostic.get("detail"))
        return parsed, ReplyShape(parsed.form, True)

    def scoped(value):
        if matched_shapes:
            foreign = foreign_agent(value, {speaker_coordinates(speaker or "")})
            if foreign is not None:
                diagnostic.update(reason="foreign_agent", detail=foreign)
                return False
        return True

    if mode == "strict":
        try:
            value = json.loads(reply)
        except (ValueError, RecursionError):
            return result(None)
        if not scoped(value):
            return result(None)
        if not isinstance(value, list):
            diagnostic.update(reason="not_list")
        elif len(value) != horizon:
            diagnostic.update(reason="wrong_length", detail=f"expected {horizon}, got {len(value)}")
        elif matched_shapes:
            for position, entry in enumerate(value, 1):
                if isinstance(entry, dict):
                    if len(entry) != 1:
                        reason = "entry_type" if not entry else "multi_key"
                        detail = (f"entry {position} is an object; use an action string or null"
                                  if not entry else f"entry {position}")
                        diagnostic.update(reason=reason, detail=detail)
                        break
                    name = next(iter(entry))
                    if speaker_coordinates(name) != speaker_coordinates(speaker or ""):
                        diagnostic.update(reason="foreign_agent", detail=str(name))
                        break
                    diagnostic.update(reason="entry_type", detail=f"entry {position} is an object; use an action string or null")
                    break
                if not own_entry(entry, syntax):
                    diagnostic.update(reason="entry_type", detail=f"entry {position} is not an action string or null")
                    break
        entries = as_sequence(value, horizon, own=True, lenient=False, syntax=syntax)
        return result(OwnReply(entries, "list") if entries is not None else None)

    read_value = partial(own_value, horizon=horizon, speaker=speaker, diagnostic=diagnostic,
                         matched_shapes=matched_shapes, pad_to_horizon=pad_to_horizon, syntax=syntax)
    try:
        value, normalized = (OWN_DECODER.decode(reply), False) if prior_shapes else decode_own_value(reply.strip())
    except (ValueError, RecursionError):
        text = reply.rsplit("EXECUTE", 1)[-1].strip()
        if horizon == 1 and (syntax.strict if prior_shapes else syntax.spaced).fullmatch(text):
            return result(read_value(text))
        prefix = None if prior_shapes else own_prefix(text, keep_tail=matched_shapes)
        if prefix is not None:
            if not scoped(prefix):
                return result(None)
            return result(read_value(prefix, embedded=reply.strip() != text))
        candidates = embedded_values(text, own=True, prior_shapes=prior_shapes, keep_tail=matched_shapes)
        if matched_shapes:
            candidates = list(candidates)
            if not all(scoped(candidate) for candidate in candidates):
                return result(None)
        for candidate in candidates:
            selected = read_value(candidate, embedded=True, prior_shapes=prior_shapes)
            if selected is not None:
                return result(selected)
        return result(None)
    if not scoped(value):
        return result(None)
    parsed = read_value(value, normalized=normalized, prior_shapes=prior_shapes)
    if parsed is None and matched_shapes and not diagnostic and not isinstance(value, (list, dict)):
        diagnostic.update(reason="not_list")
    return result(parsed)


def parse_own_reply(reply, horizon, speaker, mode, *, prior_shapes=False):
    """Compatibility facade; use :func:`read_own_reply` when diagnostics matter."""
    return read_own_reply(reply, horizon, speaker, mode, prior_shapes=prior_shapes)[0]


def matched_joint_value(value, horizon, mode, positions, syntax=SQUARE_MOVES):
    """Validate one complete joint submission, including its scope and optional lenient envelope."""
    strict = mode == "strict"
    if positions is not None:
        other = foreign_agent(value, positions)
        if other is not None:
            return None, ReplyShape(None, False, "foreign_agent", other)
    form = "joint_list"
    if isinstance(value, dict) and not strict:
        numbers = [STEP_KEY.fullmatch(key.strip()) for key in value]
        if numbers and all(numbers):
            numbered = {Decimal(match[1]): step for match, step in zip(numbers, value.values())}
            if len(numbered) != len(value):
                return None, ReplyShape(None, False, "duplicate_step", "A step number appears more than once.")
            value, form = [numbered[n] for n in sorted(numbered)], "joint_numbered"
        elif len(value) == 1 and isinstance(next(iter(value.values())), list):
            key, steps = next(iter(value.items()))
            if speaker_coordinates(key) is None:
                value, form = steps, "joint_wrapper"
            else:
                value, form = [value], "joint_object_short"
        else:
            value, form = [value], "joint_object_h1" if horizon == 1 else "joint_object_short"

    if not isinstance(value, list):
        return None, ReplyShape(None, False, "not_list")
    for index, step in enumerate(value, 1):
        if not isinstance(step, dict):
            return None, ReplyShape(None, False, "entry_type", f"Entry {index} must be a joint object.")
        seen = set()
        for name, action in step.items():
            robot = speaker_coordinates(name)
            if robot is None or (positions is not None and robot not in positions):
                return None, ReplyShape(None, False, "foreign_agent", name)
            if robot in seen:
                return None, ReplyShape(None, False, "duplicate_agent", f"{name} is assigned twice in entry {index}.")
            seen.add(robot)
            if not isinstance(action, str) or (strict and syntax.strict.fullmatch(action) is None):
                return None, ReplyShape(None, False, "entry_type", f"Entry {index} needs an action string for {name}.")
    if not value or len(value) > horizon or (strict and len(value) != horizon):
        expected = str(horizon) if strict or horizon == 1 else f"1 to {horizon}"
        return None, ReplyShape(None, False, "wrong_length", f"expected {expected}, got {len(value)}")
    return value, ReplyShape(form, True)


def read_matched_joint(reply, horizon, mode, positions, syntax=SQUARE_MOVES):
    try:
        value = OWN_DECODER.decode(reply)
    except json.JSONDecodeError:
        if mode == "lenient":
            selected = error = None
            for candidate in embedded_values(reply.rsplit("EXECUTE", 1)[-1], decoder=OWN_DECODER):
                entries, shape = matched_joint_value(candidate, horizon, mode, positions, syntax)
                if shape.reason == "foreign_agent":
                    return None, shape
                if entries is None:
                    error = error or shape
                elif selected is None:
                    selected = entries
                elif selected != entries:
                    return None, ReplyShape(None, False, "ambiguous", "The reply contains conflicting joint plans.")
            if selected is not None:
                return selected, ReplyShape("joint_fenced", True)
            if error is not None:
                return None, error
        return None, ReplyShape(None, False, "unreadable", "The reply contains no readable JSON plan.")
    except (ValueError, RecursionError) as exc:
        return None, ReplyShape(None, False, "unreadable", str(exc))
    return matched_joint_value(value, horizon, mode, positions, syntax)


_SPACE = re.compile(r"\s*")
_OWN_QUOTED = re.compile(r"'(?:\\.|[^'\\])*'", re.DOTALL)


def _cut_member(text, pos, own):
    """Read one entire member, including its own closing delimiter."""
    try:
        value, end = DECODER.raw_decode(text, pos)
        if (text[pos] not in '[{"' and end < len(text)
                and text[end] not in ",]}" and not text[end].isspace()):
            return None, None
        return value, end
    except (ValueError, RecursionError):
        if not own:
            return None, None
    # The lenient OWN reader also accepts Python-quoted list and object literals.
    if text[pos:pos + 1] in ("[", "{"):
        fragment, closed = next(embedded_fragments(text[pos:], own=True))
        if closed:
            try:
                return decode_own_value(fragment)[0], pos + len(fragment)
            except (ValueError, RecursionError):
                pass
    quote = _OWN_QUOTED.match(text, pos)
    if quote:
        try:
            return ast.literal_eval(quote[0]), quote.end()
        except (ValueError, SyntaxError):
            pass
    if re.match(r"None\b", text[pos:]):
        return None, pos + 4
    return None, None


def _cut_array(text, own, *, nested=True):
    pos = _SPACE.match(text, 1).end()
    last = count = 0
    while pos < len(text):
        _, end = _cut_member(text, pos, own)
        if end is None:
            if own and nested and not count and text[pos] == "[":
                # A single inner timeline is also accepted. Until there is an
                # inner separator, an unclosed singleton might itself be step 1.
                inner, n = _cut_array(text[pos:], own, nested=False)
                if n and (n > 1 or text[pos + len(inner) - 1:].lstrip().startswith(",")):
                    return "[" + inner + "]", n
            break
        last, count = end, count + 1
        comma = _SPACE.match(text, end).end()
        if text[comma:comma + 1] != ",":
            break
        pos = _SPACE.match(text, comma + 1).end()
    return (text[:last] + "]", count) if count else (None, 0)


def _cut_container(text, own, speaker):
    """Only supply closers belonging to a timeline or its recognized envelope."""
    if text[0] == "[":
        return _cut_array(text, own)[0]
    pos = _SPACE.match(text, 1).end()
    last = None
    while pos < len(text):
        key, end = _cut_member(text, pos, own)
        if end is None:  # possibly cut in the next numbered key
            break
        if not isinstance(key, str):
            return None
        numbered = not own and STEP_KEY.fullmatch(key.strip())
        if last is not None and not numbered:
            return None
        colon = _SPACE.match(text, end).end()
        if text[colon:colon + 1] != ":":
            break
        start = _SPACE.match(text, colon + 1).end()
        if not numbered:
            position = speaker_coordinates(key)
            wrapper = position == speaker_coordinates(speaker) if own else position is None
            if not wrapper or text[start:start + 1] != "[":
                return None  # closing this brace would manufacture a step
            _, end = _cut_member(text, start, own)
            if end is not None:
                return text[:end] + "}" if not text[end:].strip() else None
            array, _ = _cut_array(text[start:], own)
            return text[:start] + array + "}" if array else None
        _, end = _cut_member(text, start, own)
        if end is None:
            break
        last = end
        comma = _SPACE.match(text, end).end()
        if text[comma:comma + 1] != ",":
            break
        pos = _SPACE.match(text, comma + 1).end()
    return text[:last] + "}" if last else None


def cut_reply_prefix(reply, horizon, *, own, speaker, agent_positions, syntax=SQUARE_MOVES):
    """Return the short writer reply and its unpadded step count, or no usable prefix."""
    text = reply.rsplit("EXECUTE", 1)[-1].strip()
    for fragment, closed in embedded_fragments(text, own=own, cut=True):
        if not closed:
            closed_prefix = _cut_container(fragment, own, speaker) if fragment[0] in "[{" else None
            text = text[:-len(fragment)] + (closed_prefix or "")
    # Recognition uses the existing lenient shapes and scope/ambiguity checks.
    # The configured judge still sees the writer's short reply (including its
    # envelope), so strict length/format checks and ordinary repairs still apply.
    if own:
        parsed, _ = read_own_reply(text, horizon, speaker, "lenient", matched_shapes=True, pad_to_horizon=False, syntax=syntax)
        if parsed and parsed.entries:
            return text, len(parsed.entries)
    else:
        steps, _ = read_matched_joint(text, horizon, "lenient", agent_positions, syntax)
        if steps:
            return text, len(steps)
    return None


def first_object(reply):
    start = max(0, reply.rfind("EXECUTE"))
    for match in OPEN_BRACE.finditer(reply, start):
        try:
            obj, _ = DECODER.raw_decode(reply, match.start())
        except (ValueError, RecursionError):
            continue
        if isinstance(obj, dict):
            # Keep insertion order: the authors' executor applies actions in that order.
            return json.dumps(obj)
    return None


class PlanParser:
    def __init__(self, mode="lenient", mark_rescue=None, *, record_own=None, record_shape=None, syntax=SQUARE_MOVES):
        if mode not in ("lenient", "strict"):
            raise ValueError(f"Unknown parse mode {mode}")
        self.syntax = syntax
        self.mode = mode
        self.mark_rescue = mark_rescue
        self.record_own = record_own
        self.record_shape = record_shape
        self.last_shape = None

    def _shape(self, shape, enabled):
        self.last_shape = shape
        if enabled and self.record_shape is not None:
            self.record_shape(shape)

    def _select(self, reply, strict_candidate):
        selected = first_object(reply)
        if self.mark_rescue is not None and strict_candidate is not None:
            try:
                original = json.loads(strict_candidate)
                different = not isinstance(original, dict) or json.dumps(original) != selected
            except (ValueError, RecursionError):
                different = True
            if different:
                self.mark_rescue()
        return selected

    def extract(self, reply, *, revision=False, selecting=True):
        match = BRACED.search(reply)
        candidate = match.group() if match else None
        if self.mode == "strict":
            return candidate
        if not selecting:
            # HMAS-1 also uses the brace search as a dialogue-loop sentinel.
            return candidate
        # The upstream HMAS-2 revision gives the checker the whole reply if it matched.
        return self._select(reply, reply if revision and match else candidate)

    def for_check(self, reply):
        if self.mode == "strict":
            return reply
        return self._select(reply, reply)

    def sequence(self, reply, horizon, *, own=False, dialogue=False, speaker=None, legacy_own=False,
                 agent_positions=None, format_errors=None, prior_shapes=False, matched_shape=False):
        """Select a joint sequence or the submitting robot's own entries."""
        if own and not legacy_own:
            parsed, shape = read_own_reply(reply, horizon, speaker, self.mode, prior_shapes=prior_shapes,
                                           matched_shapes=matched_shape, syntax=self.syntax)
            self._shape(shape, matched_shape)
            if self.record_own is not None:
                self.record_own(parsed)
            elif parsed and parsed.rescued and self.mark_rescue is not None:
                self.mark_rescue()
            return parsed.entries if parsed else None
        if matched_shape:
            entries, shape = read_matched_joint(reply, horizon, self.mode, agent_positions, self.syntax)
            self._shape(shape, True)
            if entries is None and format_errors is not None:
                format_errors.append(shape.detail or shape.reason)
            if entries is not None and shape.form != "joint_list" and self.mark_rescue is not None:
                self.mark_rescue()
            return entries
        if dialogue:
            # EXECUTE is the DMAS protocol envelope. Strict parsing still requires a bare list inside it.
            reply = reply.rsplit("EXECUTE", 1)[-1].strip()
        try:
            value = json.loads(reply)
        except (ValueError, RecursionError):
            if self.mode == "strict":
                return None
            for candidate in embedded_values(reply.rsplit("EXECUTE", 1)[-1]):
                selected = as_sequence(candidate, horizon, own, True, agent_positions=agent_positions,
                                       format_errors=format_errors, prior_shapes=prior_shapes)
                if selected is not None:
                    if self.mark_rescue is not None:
                        self.mark_rescue()
                    return selected
            return None
        selected = as_sequence(value, horizon, own, self.mode == "lenient", agent_positions=agent_positions,
                               format_errors=format_errors, prior_shapes=prior_shapes)
        if selected is not None and not isinstance(value, list) and self.mark_rescue is not None:
            self.mark_rescue()
        return selected

"""One explicit model/provider selection shared by planner, relay and evaluators."""
from dataclasses import dataclass

DEFAULT_MODEL = 'google/gemma-4-31b-it'
DEFAULT_PROVIDER = 'DeepInfra'
MAX_TOKENS = 768


class ModelBudgetExceeded(RuntimeError):
    """Stop the run, rather than disguising a spending/call limit as fallback."""


@dataclass(frozen=True)
class ModelSelection:
    model: str = DEFAULT_MODEL
    provider: str = DEFAULT_PROVIDER
    reasoning: str = 'default'
    response_format: str = 'off'

    def __post_init__(self):
        if not self.model or '/' not in self.model or not self.provider or ',' in self.provider:
            raise ValueError('SINGLE_MODEL_PROVIDER_REQUIRED')
        if self.response_format not in ('off','json_object'):raise ValueError('UNSUPPORTED_RESPONSE_FORMAT')
        if self.reasoning not in ('default', 'off'):
            raise ValueError('UNSUPPORTED_REASONING_SETTING')

    @property
    def wire_model(self):
        return 'gemma-4-31b-it' if self.model == DEFAULT_MODEL else self.model

    @property
    def response_provider(self):
        return "DeepInfra" if self.provider.startswith("deepinfra/") else self.provider

    def request_options(self):
        value={'reasoning': {'enabled': False}} if self.reasoning == 'off' else {}
        if self.response_format!='off':value['response_format']={'type':self.response_format}
        return value


def add_model_options(parser):
    parser.add_argument('--planner-response-format',choices=('off','json_object'),default='off')
    parser.add_argument('--planner-prompt-order', choices=('off', 'static_first_v1', 'static_first_v2'), default='off')
    parser.add_argument('--planner-model', default=DEFAULT_MODEL)
    parser.add_argument('--planner-provider', default=DEFAULT_PROVIDER)
    parser.add_argument('--planner-reasoning', choices=('default', 'off'), default='default')


def selected(args):
    return ModelSelection(args.planner_model, args.planner_provider, args.planner_reasoning, args.planner_response_format)


GEMMA_FP4 = ModelSelection(DEFAULT_MODEL, 'deepinfra/turbo', 'default')
GEMMA_JSON = ModelSelection(DEFAULT_MODEL,'deepinfra/turbo','default','json_object')
DEEPSEEK = ModelSelection('deepseek/deepseek-v4.1-flash','deepinfra/fp8','off','json_object')
LING = ModelSelection('inclusionai/ling-3.0-flash-vl', 'Novita', 'off')
STATIC_KEYS = ('schema', 'robot_id', 'condition', 'task', 'order_sheet', 'static_map', 'public_rules', 'can_send_to')
DYNAMIC_KEYS = ('now_s', 'own', 'own_act_results', 'received_messages', 'events', 'candidates')


def ordered_context(context, order='off'):
    """Only insertion order changes; every key/value is preserved exactly."""
    if order == 'off': return context
    if order == 'static_first_v2':
        # Unknown fields stay in the dynamic suffix. No values, array order,
        # numeric precision, or candidate arguments are changed. In particular
        # evidence_gate contains changing archived_reports and is NOT static.
        keys = ('schema', 'public_rules', 'task', 'static_map', 'order_sheet',
                'condition', 'can_send_to', 'robot_id', 'now_s', 'own',
                'own_act_results', 'received_messages', 'events',
                'evidence_gate', 'evidence_assessment', 'candidates')
        def canonical(value):
            if isinstance(value, dict):
                return {k: canonical(value[k]) for k in sorted(value)}
            if isinstance(value, list): return [canonical(v) for v in value]
            return value
        # Extensions precede the changing observations, never the shared prefix.
        keys = keys[:8] + tuple(k for k in sorted(context) if k not in keys) + keys[8:]
        return {k: canonical(context[k]) for k in keys if k in context}
    if order != 'static_first_v1': raise ValueError('UNKNOWN_PLANNER_PROMPT_ORDER')
    keys = STATIC_KEYS + DYNAMIC_KEYS
    return {k: context[k] for k in keys if k in context} | {k: context[k] for k in sorted(context) if k not in keys}

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
        return "DeepInfra" if self.provider == "deepinfra/turbo" else self.provider

    def request_options(self):
        value={'reasoning': {'enabled': False}} if self.reasoning == 'off' else {}
        if self.response_format!='off':value['response_format']={'type':self.response_format}
        return value


def add_model_options(parser):
    parser.add_argument('--planner-response-format',choices=('off','json_object'),default='off')
    parser.add_argument('--planner-prompt-order', choices=('off', 'static_first_v1'), default='off')
    parser.add_argument('--planner-model', default=DEFAULT_MODEL)
    parser.add_argument('--planner-provider', default=DEFAULT_PROVIDER)
    parser.add_argument('--planner-reasoning', choices=('default', 'off'), default='default')


def selected(args):
    return ModelSelection(args.planner_model, args.planner_provider, args.planner_reasoning, args.planner_response_format)


GEMMA_FP4 = ModelSelection(DEFAULT_MODEL, 'deepinfra/turbo', 'default')
GEMMA_JSON = ModelSelection(DEFAULT_MODEL,'deepinfra/turbo','default','json_object')
LING = ModelSelection('inclusionai/ling-3.0-flash-vl', 'Novita', 'off')
STATIC_KEYS = ('schema', 'robot_id', 'condition', 'task', 'order_sheet', 'static_map', 'public_rules', 'can_send_to')
DYNAMIC_KEYS = ('now_s', 'own', 'own_act_results', 'received_messages', 'events', 'candidates')


def ordered_context(context, order='off'):
    """Only insertion order changes; every key/value is preserved exactly."""
    if order == 'off': return context
    if order != 'static_first_v1': raise ValueError('UNKNOWN_PLANNER_PROMPT_ORDER')
    keys = STATIC_KEYS + DYNAMIC_KEYS
    return {k: context[k] for k in keys if k in context} | {k: context[k] for k in sorted(context) if k not in keys}

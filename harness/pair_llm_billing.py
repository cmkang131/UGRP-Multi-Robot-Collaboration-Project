"""Billing of one pair request's INPUT tokens in SIM time, images included (v100).

The SIM cost of a model call is a pure function of the request and reply content and a versioned parameter
set (``zone_sim_cost.v1``, unchanged). Its input term takes ``Attempt.input_tokens``, which the CALLER
fills. The zone study fills it with the text tokens only: ``total_text_billed`` = the fixed prompt reference +
the variable user part (``fixed_prompt_equalized.v1``), so a request's two images were billed 0 tokens. That
rule is kept, byte for byte, as the text part of the bill. This module adds the image part:

    total_billed = total_text_billed + images * IMAGE_TOKENS_PER_IMAGE

``IMAGE_TOKENS_PER_IMAGE`` is a FIXED, documented constant, not a measurement taken at run time, so the charge
stays deterministic (a function of the request shape only: how many images were attached, never their bytes,
the provider's answer or the wall clock).

Versions (never edited in place; a change is a new version and a new bundle):

* ``ugrp.pair_image_billing.v1``: images billed 0 (image part absent). Used by the v97 stub smoke and by
  the v99 live smoke1 (source ``ad1dda73``, bundle sha ``a8e11294...``). Kept as history, no longer applied.
* ``ugrp.pair_image_billing.v2`` (this): 1490 tokens per image, applied from bundle ``zone-pair-llm-v100``.

Derivation of the v2 constant (smoke1, 12 real calls, ``outputs/pair-llm-v99-live/smoke1``):

* The audited proxy reports only ``prompt_tokens`` / ``completion_tokens`` / ``total_tokens``; the upstream
  per-modality breakdown (``promptTokensDetails``) is dropped, so the provider's own image token count is NOT
  observable here.
* Every request had exactly 2 images (own wrist JPEG 640x480, map figure PNG 757x599) and a local text bill of
  3,014 (first two calls) or 3,173 / 3,175 tokens (later calls). The provider counted 5,978 to 6,169 prompt
  tokens (mean 6,134.5) against a mean local text bill of 3,147.3: a residual of 2,987.2 tokens per request.
* The constant is that residual divided by the 2 images, 1,493.6, rounded to the nearest 10: **1,490**.

Read it as a calibration of this request SHAPE, not as a provider rate: the residual also holds the part of
the text the frozen local tokenizer (``ugrp.zone_study_tokens.v1``, a proxy) undercounts, and the fit has
only two text-size clusters. With exactly two images per request, billing 1,490 each makes the SIM input
bill match the provider's prompt tokens within about 0.3 percent on every smoke1 call (5,994 vs 5,980;
6,153 vs 6,159). Re-fit it, as a new version, when the model, the image sizes or the media-resolution setting
change, or when the provider's per-modality counts become available.
"""
from __future__ import annotations

from collections.abc import Mapping

from harness import zone_study_prompts_ko as pk

IMAGE_BILLING_VERSION = 'ugrp.pair_image_billing.v2'
IMAGE_TOKENS_PER_IMAGE = 1490
IMAGE_BILLING_HISTORY = (
    {'version': 'ugrp.pair_image_billing.v1', 'image_tokens_per_image': 0, 'applied': False,
     'used_by': ['zone-pair-llm-v97 stub smoke (source b201f777)',
                 'zone-pair-llm-v99 live smoke1 (source ad1dda73, bundle sha a8e112945fbad678...)'],
     'note': 'images were billed 0 tokens; kept as history, never applied again'},
)
CALIBRATION = {
    'source': 'smoke1 of zone-pair-llm-v99 (12 real calls, outputs/pair-llm-v99-live/smoke1/peer_nl)',
    'images_per_request': 2,
    'provider_prompt_tokens': {'min': 5978, 'max': 6169, 'mean': 6134.5},
    'local_text_billed_tokens': {'min': 3014, 'max': 3175, 'mean': 3147.3},
    'residual_tokens_per_request': 2987.2,
    'residual_per_image': 1493.6,
    'rounded_to': 10,
    'constant': IMAGE_TOKENS_PER_IMAGE,
    'limitation': 'the proxy reports no per-modality counts; the residual also holds local-tokenizer undercount',
}


def image_tokens(images: int) -> int:
    """The image part of the bill for ``images`` attached images."""
    if type(images) is not int or images < 0:
        raise ValueError('the image count must be a non-negative integer')
    return IMAGE_TOKENS_PER_IMAGE * images


def billed_tokens(tokens: Mapping, *, system_billed: int) -> dict:
    """The full bill of one request (text part exactly as the study's ``billed_prompt_tokens``, plus images)."""
    text_total = system_billed + tokens['user']
    image_part = image_tokens(tokens['images'])
    return {'policy': pk.FIXED_PROMPT_POLICY, 'tokenizer': tokens['tokenizer'],
            'system_actual': tokens['system'], 'system_billed': system_billed, 'user': tokens['user'],
            'images': tokens['images'], 'total_text_billed': text_total,
            'image_policy': IMAGE_BILLING_VERSION, 'image_tokens_per_image': IMAGE_TOKENS_PER_IMAGE,
            'image_tokens_billed': image_part, 'total_billed': text_total + image_part}


def billing_problems(row: Mapping) -> list:
    """The image part of an archived request's bill re-derives from its stored counts (mirror of the study's
    recount of the text part, which only knows the text keys)."""
    rid = row.get('request_id')
    billed = row.get('billed_tokens')
    if not isinstance(billed, Mapping):
        return [f'archived request {rid!r} misses billed_tokens']
    images, text_total = billed.get('images'), billed.get('total_text_billed')
    if type(images) is not int or type(text_total) is not int or images < 0:
        return [f'archived request {rid!r}: billed_tokens.images / total_text_billed are not counts']
    want = {'image_policy': IMAGE_BILLING_VERSION, 'image_tokens_per_image': IMAGE_TOKENS_PER_IMAGE,
            'image_tokens_billed': IMAGE_TOKENS_PER_IMAGE * images,
            'total_billed': text_total + IMAGE_TOKENS_PER_IMAGE * images}
    return [f'archived request {rid!r}: billed_tokens.{key} {billed.get(key)!r} != {value!r}'
            for key, value in want.items() if billed.get(key) != value]


def record() -> dict:
    """What the bundle and the study config record about the image bill."""
    return {'version': IMAGE_BILLING_VERSION, 'image_tokens_per_image': IMAGE_TOKENS_PER_IMAGE,
            'text_policy': pk.FIXED_PROMPT_POLICY, 'deterministic': True,
            'basis': 'a function of the number of attached images only; never of image bytes, provider usage or '
                     'wall time',
            'calibration': dict(CALIBRATION), 'history': [dict(row) for row in IMAGE_BILLING_HISTORY]}


__all__ = ['IMAGE_BILLING_VERSION', 'IMAGE_TOKENS_PER_IMAGE', 'IMAGE_BILLING_HISTORY', 'CALIBRATION',
           'image_tokens', 'billed_tokens', 'billing_problems', 'record']

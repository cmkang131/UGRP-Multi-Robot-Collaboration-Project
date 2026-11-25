# Box moving to target without collision

from board_sizes import LEGACY_GRIDS as SIZES, validate_board
from prompt_env1 import message_construct_func
from LLM import GPT_response
from map_events import (E2_EVENT_FILE_VERSION, EVENT_FILE_VERSION, NoAdmissibleDestination,
                        disjoint_e2, event_path, main_design, map_assignment, stratified_set)
from functools import lru_cache
from plan_parse import PlanParser
from re import error
import random
import json
import re
import copy
import numpy as np
from storage import ROOT, digest, local_path, locked, read_json, write_json

def surround_index_func(row_num, coloum_num, row_index, coloum_index):
  surround_index_list = []
  for i, j in ([row_index-1, coloum_index], [row_index+1, coloum_index], [row_index, coloum_index-1], [row_index, coloum_index+1]):
    if i>=0 and i<=row_num-1 and j>=0 and j<=coloum_num-1 and not (i == row_index and j == coloum_index):
      surround_index_list.append([i+0.5,j+0.5])
  return surround_index_list

def square_actions(items, neighbours, returned_only):
  boxes = [item for item in items if item[:3] == 'box']
  actions = []
  for box in boxes:
    actions.extend(f'move({box}, square{square})' for square in neighbours)
    if 'target' + box[3:] in items:
      actions.append(f'move({box}, target{box[3:]})')
    site = dropoff_for(box, returned_only)
    if site in items:  # Keep the version-3 order for the coloured site.
      actions.append(f'move({box}, {site})')
  if 'dropoff' in items:
    actions.extend(f'move({box}, dropoff)' for box in boxes)
  return actions


def state_update_func(pg_row_num, pg_column_num, pg_dict, returned_only=False):
  state_update_prompt = ''
  for i in range(pg_row_num):
    for j in range(pg_column_num):
      square_item_list = pg_dict[str(i+0.5)+'_'+str(j+0.5)]
      surround_index_list = surround_index_func(pg_row_num, pg_column_num, i, j)
      state_update_prompt += f'Agent[{i+0.5}, {j+0.5}]: I am in square[{i+0.5}, {j+0.5}], I can observe {square_item_list}, I can do '
      action_list = square_actions(square_item_list, surround_index_list, returned_only)
      state_update_prompt += f'{action_list}\n'
  return state_update_prompt

def state_update_func_local_agent(pg_row_num, pg_column_num, pg_row_i, pg_column_j, pg_dict, returned_only=False):
  state_update_prompt_local_agent = ''
  state_update_prompt_other_agent = ''

  for i in range(pg_row_num):
    for j in range(pg_column_num):
      if not (i == pg_row_i and pg_column_j == j):
        square_item_list = pg_dict[str(i+0.5)+'_'+str(j+0.5)]
        surround_index_list = surround_index_func(pg_row_num, pg_column_num, i, j)
        state_update_prompt_other_agent += f'Agent[{i+0.5}, {j+0.5}]: I am in square[{i+0.5}, {j+0.5}], I can observe {square_item_list}, I can do '
        action_list = square_actions(square_item_list, surround_index_list, returned_only)
        state_update_prompt_other_agent += f'{action_list}\n'

  square_item_list = pg_dict[str(pg_row_i+0.5)+'_'+str(pg_column_j+0.5)]
  surround_index_list = surround_index_func(pg_row_num, pg_column_num, pg_row_i, pg_column_j)
  state_update_prompt_local_agent += f'Agent[{pg_row_i+0.5}, {pg_column_j+0.5}]: in square[{pg_row_i+0.5}, {pg_column_j+0.5}], can observe {square_item_list}, can do '
  action_list = square_actions(square_item_list, surround_index_list, returned_only)
  state_update_prompt_local_agent += f'{action_list}\n'
  return state_update_prompt_local_agent, state_update_prompt_other_agent

def plan_feedback(pg_dict_input, selected, response, returned_only=False):
  """The authors' single-proposal feasibility check, before issuing a repair call."""
  try:
    original_response_dict = json.loads(selected)

    pg_dict_original = copy.deepcopy(pg_dict_input)
    transformed_dict = {}
    for key, value in original_response_dict.items():
      coordinates = tuple(map(float, re.findall(r"\d+\.?\d*", key)))

      # match the item and location in the value
      match = re.match(r"move\((.*?),\s(.*?)\)", value)
      if match:
        item, location = match.groups()

        if "square" in location:
          location = tuple(map(float, re.findall(r"\d+\.?\d*", location)))

        transformed_dict[coordinates] = [item, location]

    feedback = ''
    for key, value in transformed_dict.items():
      # print(f"Key: {key}, Value1: {value[0]}, Value2: {value[1]}")
      if value[0] in pg_dict_original[str(key[0]) + '_' + str(key[1])] and type(value[1]) == tuple and not value[0].startswith('dropoff') and (
              (np.abs(key[0] - value[1][0]) == 0 and np.abs(key[1] - value[1][1]) == 1) or (
              np.abs(key[0] - value[1][0]) == 1 and np.abs(key[1] - value[1][1]) == 0)):
        pass
      elif value[0] in pg_dict_original[str(key[0]) + '_' + str(key[1])] and type(value[1]) == str and value[1] in \
              pg_dict_original[str(key[0]) + '_' + str(key[1])] and value[0][:4] == 'box_' and value[1][
                                                                                               :7] == 'target_' and \
              value[0][4:] == value[1][7:]:
        pass
      elif is_dropoff(pg_dict_original[str(key[0]) + '_' + str(key[1])], value, returned_only):
        pass
      else:
        # print(f"Error, Iteration Num: {iteration_num}, Key: {key}, Value1: {value[0]}, Value2: {value[1]}")
        feedback += f'Your assigned task for {key[0]}_{key[1]} is not in the doable action list; '
  except Exception:
    if selected is not None:
      raise error(f'The response in wrong json format: {response}')
    feedback = 'Your assigned plan is not in the correct json format as before. If your answer is empty dict, please check whether you miss to move box into the same colored target like move(box_blue, target_blue)'
  return feedback


MAX_REPAIRS = 6


def with_action_syntactic_check_func(pg_dict_input, response, user_prompt_list_input, response_total_list_input, model_name, dialogue_history_method, cen_decen_framework, *, parser=None, returned_only=False):
  parser = parser or PlanParser()
  user_prompt_list = copy.deepcopy(user_prompt_list_input)
  response_total_list = copy.deepcopy(response_total_list_input)
  iteration_num = 0
  token_num_count_list_add = []
  while iteration_num < MAX_REPAIRS:
    selected = parser.for_check(response)
    response_total_list.append(response if selected is None else selected)
    feedback = plan_feedback(pg_dict_input, selected, response, returned_only)

    if feedback != '':
      feedback += 'Please replan for all the agents again with the same ouput format:'
      user_prompt_list.append(feedback)
      messages = message_construct_func(user_prompt_list, response_total_list, dialogue_history_method) # message construction
      response, token_num_count = GPT_response(messages, model_name)
      token_num_count_list_add.append(token_num_count)
      if response == 'Out of tokens':
        return response, token_num_count_list_add
      iteration_num += 1
    else:
      return selected, token_num_count_list_add
  return 'Syntactic Error', token_num_count_list_add

def dropoff_for(box, returned_only):
  if returned_only:
    if not box.endswith('_returned'):
      return None
    box = box.removesuffix('_returned')
  return 'dropoff_' + box[4:]


def is_dropoff(items, value, returned_only):
  box, destination = value
  return (box in items and box.startswith('box_') and destination in items and
          (destination == 'dropoff' or destination == dropoff_for(box, returned_only)))


def action_from_response(pg_dict_input, original_response_dict, applied=None, *, returned_only=False):
  system_error_feedback = ''
  pg_dict_original = copy.deepcopy(pg_dict_input)
  transformed_dict = {}
  for key, value in original_response_dict.items():
    coordinates = tuple(map(float, re.findall(r"\d+\.?\d*", key)))

    # match the item and location in the value
    match = re.match(r"move\((.*?),\s(.*?)\)", value)
    if match:
      item, location = match.groups()
      if "square" in location:
          location = tuple(map(float, re.findall(r"\d+\.?\d*", location)))
      transformed_dict[coordinates] = [item, location]

  for key, value in transformed_dict.items():
    #print(f"Key: {key}, Value1: {value[0]}, Value2: {value[1]}")
    if value[0] in pg_dict_original[str(key[0])+'_'+str(key[1])] and type(value[1]) == tuple and not value[0].startswith('dropoff') and ((np.abs(key[0]-value[1][0])==0 and np.abs(key[1]-value[1][1])==1) or (np.abs(key[0]-value[1][0])==1 and np.abs(key[1]-value[1][1])==0)):
      pg_dict_original[str(key[0])+'_'+str(key[1])].remove(value[0])
      pg_dict_original[str(value[1][0])+'_'+str(value[1][1])].append(value[0])
    elif value[0] in pg_dict_original[str(key[0])+'_'+str(key[1])] and type(value[1]) == str and value[1] in pg_dict_original[str(key[0])+'_'+str(key[1])] and value[0][:4] == 'box_' and value[1][:7] == 'target_' and value[0][4:] == value[1][7:]:
      pg_dict_original[str(key[0])+'_'+str(key[1])].remove(value[0])
      pg_dict_original[str(key[0])+'_'+str(key[1])].remove(value[1])
    elif is_dropoff(pg_dict_original[str(key[0])+'_'+str(key[1])], value, returned_only):
      pg_dict_original[str(key[0])+'_'+str(key[1])].remove(value[0])
    else:
      #print(f"Error, Iteration Num: {iteration_num}, Key: {key}, Value1: {value[0]}, Value2: {value[1]}")
      system_error_feedback += f'Your assigned task for {key[0]}_{key[1]} is not in the doable action list; '
      continue
    if applied is not None:
      applied.append((key, *value))

  return system_error_feedback, pg_dict_original

def env_create(pg_row_num = 5, pg_column_num = 5, box_num_low_bound = 2, box_num_upper_bound = 2, color_list = ['blue', 'red', 'green', 'purple', 'orange'], *, rng=random, box_counts=None):
  # pg_dict records the items in each square over steps, here in the initial setting, we randomly assign items into each square
  pg_dict = {}
  for i in range(pg_row_num):
    for j in range(pg_column_num):
      pg_dict[str(i+0.5)+'_'+str(j+0.5)] = []

  for color in color_list:
    box_num = (box_counts[color] if box_counts is not None else
               rng.randint(box_num_low_bound, box_num_upper_bound))
    for _ in range(box_num):
      N_box = rng.randint(0, pg_row_num*pg_column_num - 1)
      a_box = N_box // pg_column_num
      b_box = N_box % pg_column_num
      N_target = rng.randint(0, pg_row_num*pg_column_num - 1)
      a_target = N_target // pg_column_num
      b_target = N_target % pg_column_num
      pg_dict[str(a_box+0.5)+'_'+str(b_box+0.5)].append('box_' + color)
      pg_dict[str(a_target+0.5)+'_'+str(b_target+0.5)].append('target_' + color)
  return pg_dict

@lru_cache(maxsize=4)
def main_maps(rows, cols, map_set="main"):
    design = main_design(rows, cols, map_set)
    replacement = max(design) + 1
    # Earlier confirmation replacements can occupy generation seeds in the new slot range.
    enrolled = ({event["seed"] for _, event in main_maps(rows, cols, "confirm").values()}
                if map_set == "cause" else set())
    maps = {}
    for slot in sorted(design):
        stratum, wording = design[slot]
        seed, skipped = slot, []
        while True:
            if seed not in enrolled:
                state = env_create(rows, cols, 1, 3, rng=random.Random(seed))
                sha = digest((json.dumps(state, indent=2) + "\n").encode())
                try:
                    event = map_assignment(state, seed, sha, rows, cols, action_from_response, stratum=stratum)
                    break
                except NoAdmissibleDestination:
                    pass
            skipped.append(seed)
            seed = replacement
            replacement += 1
        row, col = map(int, event["D"])
        event.update(map_set=map_set, slot_seed=slot, skipped_seeds=skipped, stratum=stratum,
                     member_position=row * cols + col + 1, wording=wording)
        if map_set == "cause":
            event["previously_enrolled_seeds"] = [s for s in skipped if s in enrolled]
        maps[slot] = state, event
    return maps


def saved_env(rows, cols, seed, directory=ROOT / 'envs'):
  """Generate a missing seed once. An enrolled file must still match its digest."""
  validate_board(f"{rows}x{cols}", "legacy")
  directory = local_path(directory)
  directory.mkdir(parents=True, exist_ok=True)
  relative = f'{rows}x{cols}/env{seed}.json'
  path = directory / relative
  map_set = stratified_set(rows, cols, seed)
  manifest_path = directory / 'manifest.json'
  with locked(directory / '.env.lock'):
    manifest = read_json(manifest_path) if manifest_path.exists() else {}
    if relative in manifest:
      if not path.is_file() or digest(path.read_bytes()) != manifest[relative]:
        raise ValueError(f'Missing or modified enrolled environment: {relative}')
    else:
      if path.exists():
        raise ValueError(f'Unregistered environment already exists: {relative}')
      state = main_maps(rows, cols, map_set)[seed][0] if map_set else env_create(rows, cols, 1, 3, rng=random.Random(seed))
      path.parent.mkdir(parents=True, exist_ok=True)
      write_json(path, state)
      manifest[relative] = digest(path.read_bytes())
      write_json(manifest_path, manifest)
    # Version-one maps are enrolled once without rewriting their bytes or their manifest.
    sidecar = event_path(path)
    event_manifest_path = directory / 'events-manifest.json'
    events = read_json(event_manifest_path) if event_manifest_path.exists() else {}
    key = sidecar.relative_to(directory).as_posix()
    if key in events:
      if not sidecar.is_file() or digest(sidecar.read_bytes()) != events[key]:
        raise ValueError(f'Missing or modified enrolled event: {key}')
      event = read_json(sidecar)
      if event.get('event_file_version') != EVENT_FILE_VERSION:
        raise ValueError(f'Event file requires re-enrolment: {key}')
      if map_set and event != main_maps(rows, cols, map_set)[seed][1]:
        raise ValueError(f'Existing event conflicts with the stratified {map_set} set: {key}')
    else:
      assignment = (main_maps(rows, cols, map_set)[seed][1] if map_set else
                    map_assignment(read_json(path), seed, manifest[relative], rows, cols, action_from_response))
      if assignment['env_sha256'] != manifest[relative]:
        raise ValueError(f'Enrolled environment differs from its seeded assignment: {relative}')
      if sidecar.exists():
        if read_json(sidecar) != assignment:
          raise ValueError(f'Unregistered event differs from seeded assignment: {key}')
      else:
        write_json(sidecar, assignment)
      events[key] = digest(sidecar.read_bytes())
      write_json(event_manifest_path, events)
    if map_set:
      revised = event_path(path, E2_EVENT_FILE_VERSION)
      revised_key = revised.relative_to(directory).as_posix()
      state, base = main_maps(rows, cols, map_set)[seed]
      expected = disjoint_e2(state, base, events[key])
      if revised.exists():
        if read_json(revised) != expected:
          raise ValueError(f'Modified e2 assignment: {revised_key}')
      elif revised_key in events:
        raise ValueError(f'Missing enrolled e2 assignment: {revised_key}')
      else:
        write_json(revised, expected)
      sha = digest(revised.read_bytes())
      if revised_key not in events:
        events[revised_key] = sha
        write_json(event_manifest_path, events)
      elif events[revised_key] != sha:
        raise ValueError(f'Modified enrolled event: {revised_key}')
    return path, manifest[relative]


def create_env1(Saving_path, repeat_num=10):
  for rows, cols in SIZES:
    for seed in range(repeat_num):
      saved_env(rows, cols, seed, Saving_path)

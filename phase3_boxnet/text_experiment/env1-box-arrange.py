import json
import os
import re
from functools import partial
from LLM import GPT_response
from planning_metrics import ENV_STEP_LIMIT
from env1_create import (action_from_response, state_update_func, state_update_func_local_agent,
                         with_action_syntactic_check_func)
from prompt_env1 import (input_prompt_1_func_total, input_prompt_local_agent_DMAS_dialogue_func,
                         input_prompt_local_agent_HMAS1_dialogue_fast_plan_func,
                         input_prompt_local_agent_HMAS1_dialogue_func, input_prompt_local_agent_HMAS2_dialogue_func,
                         message_construct_func)

# cen_decen_framework = 'DMAS', 'HMAS-1', 'CMAS', 'HMAS-2'
# dialogue_history_method = '_w_all_dialogue_history', '_wo_any_dialogue_history', '_w_only_state_action_history'
def run_exp(Saving_path_result, pg_dict, pg_row_num, pg_column_num, query_time_limit,
            runtime, cen_decen_framework, model_name,
            dialogue_history_method='_w_only_state_action_history', *, history_window=None, cmas_history=False):

  if history_window == 0:
    dialogue_history_method = '_wo_any_dialogue_history'

  # specify the path to your dir for saving the results
  os.makedirs(Saving_path_result, exist_ok=True)
  os.makedirs(Saving_path_result+f'/prompt', exist_ok=True)
  os.makedirs(Saving_path_result+f'/response', exist_ok=True)
  os.makedirs(Saving_path_result+f'/pg_state', exist_ok=True)
  os.makedirs(Saving_path_result + f'/dialogue_history', exist_ok=True)

  user_prompt_list = [] # The record list of all the input prompts
  response_total_list = [] # The record list of all the responses
  pg_state_list = [] # The record list of apg states in varied steps
  dialogue_history_list = []
  token_num_count_list = []
  pg_state_list.append(pg_dict)
  with open(Saving_path_result+'/pg_state' + '/pg_state'+str(1)+'.json', 'w') as f:
      json.dump(pg_dict, f)
  if runtime.spec.max_env_steps == 0:
    return 'success' if runtime.boxes_left == 0 else ENV_STEP_LIMIT
  runtime.relay_after_step(0)
  plan_call = None

  # Bind only the two experiment settings used by all of the authors' check sites.
  returned_only = runtime.condition == 'e2'
  check_plan = partial(with_action_syntactic_check_func, parser=runtime.parser, returned_only=returned_only)

  ### Start the Game! Query LLM for response
  for index_query_times in range(query_time_limit): # The upper limit of calling LLMs
    runtime.begin_iteration(index_query_times + 1)
    state_update_prompt = state_update_func(pg_row_num, pg_column_num, pg_dict, returned_only)
    if cen_decen_framework in ('DMAS'):
      match = None
      count_round = 0
      dialogue_history = ''
      response = '{}'
      plan_call = None
      while not match and count_round <= 3:
        count_round += 1
        runtime.set_round(count_round)
        for local_agent_row_i in range(pg_row_num):
          for local_agent_column_j in range(pg_column_num):
            #if f'Agent[{local_agent_row_i + 0.5}, {local_agent_column_j + 0.5}]' in pg_dict:
              state_update_prompt_local_agent, state_update_prompt_other_agent = state_update_func_local_agent(pg_row_num,
                                                                                                               pg_column_num,
                                                                                                               local_agent_row_i,
                                                                                                               local_agent_column_j,
                                                                                                               pg_dict, returned_only)
              user_prompt_1 = input_prompt_local_agent_DMAS_dialogue_func(state_update_prompt_local_agent,
                                                                           state_update_prompt_other_agent,
                                                                           dialogue_history, response_total_list,
                                                                           pg_state_list, dialogue_history_list,
                                                                           dialogue_history_method, announcement=runtime.address_local(local_agent_row_i, local_agent_column_j),
                                                                           history_window=history_window, state_position=runtime.spec.state_position)
              user_prompt_1 = runtime.with_messages(user_prompt_1)
              user_prompt_list.append(user_prompt_1)
              with open(Saving_path_result + '/prompt' + '/user_prompt_' + str(index_query_times + 1), 'w') as f:
                f.write(user_prompt_list[-1])
              messages = message_construct_func([user_prompt_1], [], '_w_all_dialogue_history')
              initial_response, token_num_count = GPT_response(messages,model_name)  # 'gpt-4' or 'gpt-3.5-turbo-0301' or 'gpt-4-32k' or 'gpt-3' or 'gpt-4-0613'
              token_num_count_list.append(token_num_count)

              dialogue_history += f'[Agent[{local_agent_row_i+0.5}, {local_agent_column_j+0.5}]: {initial_response}]\n\n'
              #print(dialogue_history)
              execute = re.search(r'EXECUTE', initial_response)
              if execute:
                # Search for the pattern that starts with { and ends with }
                match = runtime.parser.extract(initial_response)
                if match:
                  response = match
                  response, token_num_count_list_add = check_plan(pg_dict, response,
                                                                                        [user_prompt_list[-1]],
                                                                                        [],
                                                                                        model_name,
                                                                                        '_w_all_dialogue_history',
                                                                                        cen_decen_framework)
                  token_num_count_list = token_num_count_list + token_num_count_list_add
                  plan_call = runtime.session.cursor
                  #print(f'User prompt: {user_prompt_1}\n\n')
              runtime.finish_dialogue_turn()
              if execute:
                break
      dialogue_history_list.append(dialogue_history)
    else:
      if cen_decen_framework in ('CMAS', 'HMAS-1', 'HMAS-1-fast', 'HMAS-2'):
        user_prompt_1 = input_prompt_1_func_total(state_update_prompt, response_total_list,
                                  pg_state_list, dialogue_history_list,
                                  dialogue_history_method, cen_decen_framework, announcement=runtime.address_central(),
                                  history_window=history_window, cmas_history=cmas_history)
        user_prompt_1 = runtime.with_messages(user_prompt_1)
        user_prompt_list.append(user_prompt_1)

        messages = message_construct_func([user_prompt_1], [], '_w_all_dialogue_history') # message construction

      with open(Saving_path_result+'/prompt' + '/user_prompt_'+str(index_query_times+1), 'w') as f:
        f.write(user_prompt_list[-1])
      initial_response, token_num_count = GPT_response(messages, model_name) # 'gpt-4' or 'gpt-3.5-turbo-0301' or 'gpt-4-32k' or 'gpt-3' or 'gpt-4-0613'
      token_num_count_list.append(token_num_count)
      match = runtime.parser.extract(initial_response)
      if match:
        response = match
        if response[0] == '{' and response[-1] == '}':
          response, token_num_count_list_add = check_plan(pg_dict, response, [user_prompt_1], [], model_name, '_w_all_dialogue_history', cen_decen_framework)
          token_num_count_list = token_num_count_list + token_num_count_list_add
          plan_call = runtime.session.cursor
        else:
          raise ValueError(f'Response format error: {response}')

      if not match and initial_response == 'Out of tokens':
        return 'failure over token length limit'
      if not match and index_query_times == 0:
        return 'Hallucination of wrong plan'
      if response == 'Out of tokens':
        success_failure = 'failure over token length limit'
        return success_failure
      elif response == 'Syntactic Error':
        success_failure = 'Syntactic Error'
        return success_failure

      # Local agent response for checking the feasibility of actions
      if cen_decen_framework == 'HMAS-2':
        dialogue_history = f'Central Planner: {response}\n'
        #print(f'Original plan response: {response}')
        prompt_list_dir = {}; response_list_dir = {}; local_agent_response_list_dir = {}
        local_agent_response_list_dir['feedback1'] = ''
        agent_dict = json.loads(response)
        runtime.iterations[-1]["central_plan_agents"] = list(agent_dict)
        for local_agent_row_i in range(pg_row_num):
          for local_agent_column_j in range(pg_column_num):
            if f'Agent[{local_agent_row_i+0.5}, {local_agent_column_j+0.5}]' in agent_dict:
              runtime.set_round(1)
              prompt_list_dir[f'Agent[{local_agent_row_i+0.5}, {local_agent_column_j+0.5}]'] = []
              response_list_dir[f'Agent[{local_agent_row_i+0.5}, {local_agent_column_j+0.5}]'] = []
              state_update_prompt_local_agent, state_update_prompt_other_agent = state_update_func_local_agent(pg_row_num, pg_column_num, local_agent_row_i, local_agent_column_j, pg_dict, returned_only)

              local_reprompt = input_prompt_local_agent_HMAS2_dialogue_func(state_update_prompt_local_agent, state_update_prompt_other_agent, response, response_total_list, pg_state_list, dialogue_history_list, dialogue_history_method, announcement=runtime.address_local(local_agent_row_i, local_agent_column_j), history_window=history_window)
              local_reprompt = runtime.with_messages(local_reprompt)
              prompt_list_dir[f'Agent[{local_agent_row_i+0.5}, {local_agent_column_j+0.5}]'].append(local_reprompt)
              messages = message_construct_func(prompt_list_dir[f'Agent[{local_agent_row_i+0.5}, {local_agent_column_j+0.5}]'], response_list_dir[f'Agent[{local_agent_row_i+0.5}, {local_agent_column_j+0.5}]'], '_w_all_dialogue_history')
              response_local_agent, token_num_count = GPT_response(messages, model_name)
              token_num_count_list.append(token_num_count)
              #print(f'Agent[{local_agent_row_i+0.5}, {local_agent_column_j+0.5}] response: {response_local_agent}')
              if response_local_agent != 'I Agree':
                local_agent_response_list_dir['feedback1'] += f'Agent[{local_agent_row_i+0.5}, {local_agent_column_j+0.5}]: {response_local_agent}\n' # collect the response from all the local agents
                dialogue_history += f'Agent[{local_agent_row_i+0.5}, {local_agent_column_j+0.5}]: {response_local_agent}\n'

        if local_agent_response_list_dir['feedback1'] != '':
          local_agent_response_list_dir['feedback1'] += '\nThis is the feedback from local agents. If you find some errors in your previous plan, try to modify it. Otherwise, output the same plan as before. The output should have the same json format {Agent[0.5, 0.5]:move(box_blue, square[0.5, 1.5]), Agent[1.5, 0.5]:move...}, as above. Do not explain, just directly output json directory. Your response:'
          messages = message_construct_func([user_prompt_list[-1], local_agent_response_list_dir['feedback1']], [response], '_w_all_dialogue_history') # message construction
          runtime.address_central()
          response_central_again, token_num_count = GPT_response(messages, model_name)
          token_num_count_list.append(token_num_count)
          match = runtime.parser.extract(response_central_again, revision=True)
          if match:
            response = match
            response, token_num_count_list_add = check_plan(pg_dict, response_central_again, [user_prompt_list[-1], local_agent_response_list_dir['feedback1']], [response], model_name,
                                                      '_w_all_dialogue_history', cen_decen_framework)
            token_num_count_list = token_num_count_list + token_num_count_list_add
            plan_call = runtime.session.cursor
          #print(messages[2])
          #print(messages[3])

        dialogue_history_list.append(dialogue_history)

      elif cen_decen_framework == 'HMAS-1' or cen_decen_framework == 'HMAS-1-fast':
        count_round = 0
        dialogue_history = f'Central Planner: {response}\n'
        match = None
        agent_dict = json.loads(response)
        while not match and count_round <= 3:
          count_round += 1
          runtime.set_round(count_round)
          for local_agent_row_i in range(pg_row_num):
            for local_agent_column_j in range(pg_column_num):
              if f'Agent[{local_agent_row_i + 0.5}, {local_agent_column_j + 0.5}]' in agent_dict:
                state_update_prompt_local_agent, state_update_prompt_other_agent = state_update_func_local_agent(
                  pg_row_num,
                  pg_column_num,
                  local_agent_row_i,
                  local_agent_column_j,
                  pg_dict, returned_only)
                if count_round >= 2 and cen_decen_framework == 'HMAS-1-fast':
                  user_prompt_1 = input_prompt_local_agent_HMAS1_dialogue_fast_plan_func(state_update_prompt_local_agent,
                                                                               state_update_prompt_other_agent,
                                                                               dialogue_history, response_total_list, pg_state_list,
                                                                               dialogue_history_list, dialogue_history_method,
                                                                               initial_plan=response, history_window=history_window)
                else:
                  user_prompt_1 = input_prompt_local_agent_HMAS1_dialogue_func(state_update_prompt_local_agent,
                                                               state_update_prompt_other_agent, dialogue_history,
                                                               response_total_list, pg_state_list,
                                                               dialogue_history_list, dialogue_history_method,
                                                               initial_plan='', announcement=runtime.address_local(local_agent_row_i, local_agent_column_j),
                                                               history_window=history_window)

                user_prompt_1 = runtime.with_messages(user_prompt_1)
                user_prompt_list.append(user_prompt_1)
                with open(Saving_path_result + '/prompt' + '/user_prompt_' + str(index_query_times + 1), 'w') as f:
                  f.write(user_prompt_list[-1])
                messages = message_construct_func([user_prompt_1], [], '_w_all_dialogue_history')
                initial_response, token_num_count = GPT_response(messages,model_name)  # 'gpt-4' or 'gpt-3.5-turbo-0301' or 'gpt-4-32k' or 'gpt-3' or 'gpt-4-0613'
                token_num_count_list.append(token_num_count)

                #print('-----------prompt------------\n' + initial_response)
                dialogue_history += f'Agent[{local_agent_row_i + 0.5}, {local_agent_column_j + 0.5}]: {initial_response}\n'
                #print(dialogue_history)
                match = runtime.parser.extract(initial_response, selecting='EXECUTE' in initial_response)
                execute = match and 'EXECUTE' in initial_response
                if execute:
                  response = match
                  response, token_num_count_list_add = check_plan(pg_dict, response,
                                                                                        [user_prompt_list[-1]],
                                                                                        [],
                                                                                        model_name,
                                                                                        '_w_all_dialogue_history',
                                                                                        cen_decen_framework)
                  token_num_count_list = token_num_count_list + token_num_count_list_add
                  plan_call = runtime.session.cursor
                runtime.finish_dialogue_turn()
                if execute:
                  break
        dialogue_history_list.append(dialogue_history)

    response_total_list.append(response)
    if response == 'Out of tokens':
      success_failure = 'failure over token length limit'
      return success_failure
    elif response == 'Syntactic Error':
      success_failure = 'Syntactic Error'
      return success_failure

    runtime.finish_planning()
    data = json.loads(response)
    
    with open(Saving_path_result+'/response' + '/response'+str(index_query_times+1)+'.json', 'w') as f:
        json.dump(data, f)
    original_response_dict = json.loads(response_total_list[index_query_times])
    if cen_decen_framework in ('DMAS', 'HMAS-1', 'HMAS-1-fast'):
      with open(Saving_path_result+'/dialogue_history' + '/dialogue_history'+str(index_query_times)+'.txt', 'w') as f:
          f.write(dialogue_history_list[index_query_times])
    try:
      applied = []
      system_error_feedback, pg_dict_returned = action_from_response(pg_dict, original_response_dict, applied, returned_only=returned_only)
      pg_dict = pg_dict_returned

    except (ValueError, TypeError, KeyError, IndexError):
      success_failure = 'Hallucination of wrong plan'
      return success_failure
    pg_dict = runtime.executed(pg_dict, data, applied, system_error_feedback, plan_call)
    pg_state_list.append(pg_dict)
    with open(Saving_path_result+'/pg_state' + '/pg_state'+str(index_query_times+2)+'.json', 'w') as f:
        json.dump(pg_dict, f)
    runtime.relay_after_step(index_query_times + 1)

    if runtime.condition != 'static' or runtime.spec.dropoff == 'always':
      count = runtime.boxes_left
    else:
      count = sum(len(value) for value in pg_dict.values())
    if count == 0:
      break
    if index_query_times + 1 == runtime.spec.max_env_steps:
      return ENV_STEP_LIMIT

  if index_query_times < query_time_limit - 1:
    success_failure = 'success'
  else:
    success_failure = 'failure over query time limit'
  return success_failure

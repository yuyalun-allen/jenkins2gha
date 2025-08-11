import re
from typing import List, Dict, Any
from converter.parse.parse_steps import parse_jenkins_steps
from converter.convert.convert_stage import GitHubActionsConverter
from converter.utils.extract_block import extract_block
from converter.utils.getLogger import setup_logging
from converter.utils.split_steps_content import split_steps_content
from converter.utils.normalize_job_name import normalize_identifier
from converter.plugins.load_plugins import load_plugins
from converter.parse import parse_environment
from converter.parse.parse_tool import tool_to_yaml
from converter.parse.parse_post import post_to_yaml
from converter.parse.parse_environment import environment_to_yaml
from converter.parse.parse_option import option_to_yaml
from converter.parse.parse_matrix import convert_jenkins_matrix
from converter.parse.parse_when import convert_jenkins_when_to_gha
logger = setup_logging()


def merge_configs(parent_obj, child_obj):
    """
    安全合并：
    1. 如果 parent/child 都是 None，就返回 None
    2. 如果 parent 是 list, child 是 list => list + list
    3. 如果 parent 是 dict, child 是 dict => dict.update(dict)
    4. 如果类型不一致 => 以 child_obj 覆盖
    5. 如果 parent 或 child 是 None => 另一个直接返回

    你也可以自定义别的策略，比如先把 list 转成 dict 等等。
    """
    # 情况0：都有值都是 None
    if parent_obj is None and child_obj is None:
        return None

    # 情况1：有一个是 None
    if parent_obj is None:
        return child_obj
    if child_obj is None:
        return parent_obj

    # 情况2：都是 list
    if isinstance(parent_obj, list) and isinstance(child_obj, list):
        return parent_obj + child_obj

    # 情况3：都是 dict
    if isinstance(parent_obj, dict) and isinstance(child_obj, dict):
        merged = dict(parent_obj)
        merged.update(child_obj)
        return merged

    # 情况4：类型不一致
    if isinstance(parent_obj, dict) and isinstance(child_obj, list) and not child_obj:
        # 如果 parent 是字典，而 child 是空列表，则保留 parent
        return parent_obj
    elif isinstance(parent_obj, list) and isinstance(child_obj, dict) and not parent_obj:
        # 如果 parent 是空列表，而 child 是字典，则使用 child
        return child_obj
    else:
        # 其他类型不一致情况，仍然以 child 覆盖
        return child_obj


def _parse_stages_in_parallel_block(
        parallel_block_content: str,
        parent_when: Dict[str, Any],
        parent_tools: Dict[str, Any],
        parent_env: Dict[str, Any],
        parent_options: Dict[str, Any],
        parent_post: List[Dict[str, Any]],
        parent_matrix: Dict[str, Any],
        processed_stages: dict  # 修改为字典，键为stage名称，值为stage信息
) -> List[Dict[str, Any]]:
    """
    当外层 stage 检测到 parallel { ... } 块时，调用本函数：
    1. 从 parallel_block_content 中解析出所有的子 stage('xxx'){ ... }；
    2. 为每个子 stage 合并外层 stage 的 when、tools、env 等元信息；
    3. 返回这些平行子 stage 组成的列表。
    """
    sub_stages = []

    # 匹配每个 parallel 内部的 stage
    stage_pattern = re.compile(r'stage\s*\(\s*[\'"](.+?)[\'"]\s*\)\s*\{', re.DOTALL)
    stage_matches = list(stage_pattern.finditer(parallel_block_content))

    for i, stage_match in enumerate(stage_matches):
        sub_stage_name = stage_match.group(1)

        # 如果已经处理过这个stage名称，则跳过
        if sub_stage_name in processed_stages:
            logger.info(f"并行stage已处理过: {sub_stage_name}")
            continue

        logger.info(f"处理并行stage: {sub_stage_name}")
        sub_stage_start = stage_match.end()

        # 逐字符匹配大括号，找到这个子 stage 的主体
        brace_count = 1
        pos = sub_stage_start
        while pos < len(parallel_block_content) and brace_count > 0:
            c = parallel_block_content[pos]
            if c == '{':
                brace_count += 1
            elif c == '}':
                brace_count -= 1
            pos += 1

        sub_stage_body = parallel_block_content[sub_stage_start:pos - 1].strip()
        logger.info(f"Parallel sub_stage_body: {sub_stage_body}")

        # ---- 解析这个子 stage 内部的各种信息（steps / when / tools / env / option / matrix / post）----
        tools_yaml = tool_to_yaml(sub_stage_body, "stage") or []
        post_yaml = post_to_yaml(sub_stage_body, [], "stage") or []
        env_yaml = environment_to_yaml(sub_stage_body, "stage") or {}
        option_yaml = option_to_yaml(sub_stage_body, "stage") or []
        matrix_yaml = convert_jenkins_matrix(sub_stage_body) or {}
        when_yaml = convert_jenkins_when_to_gha(sub_stage_body) or {}

        # ---- 合并外层 stage 的元信息到子 stage 中 ----
        final_when = merge_configs(parent_when, when_yaml)
        final_tools = merge_configs(parent_tools, tools_yaml)
        final_env = merge_configs(parent_env, env_yaml)
        final_options = merge_configs(parent_options, option_yaml)
        final_post = merge_configs(parent_post, post_yaml)
        final_matrix = merge_configs(parent_matrix, matrix_yaml)

        # ---- 解析 steps 块 ----
        steps_content = extract_block(sub_stage_body, 'steps')
        steps = parse_jenkins_steps(steps_content)
        logger.info(f"Parallel steps: {steps}")

        # 创建stage信息
        stage_info = {
            'name': sub_stage_name,
            'steps': steps,
            'tools': final_tools,
            'post': final_post,
            'env': final_env,
            'option': final_options,
            'matrix': final_matrix,
            'when': final_when,
        }

        # 将stage信息保存到字典中，以后可以直接使用
        processed_stages[sub_stage_name] = stage_info
        sub_stages.append(stage_info)

    return sub_stages


def _parse_stages_in_nested_block(
        nested_stages_content: str,
        parent_when: Dict[str, Any],
        parent_tools: Dict[str, Any],
        parent_env: Dict[str, Any],
        parent_options: Dict[str, Any],
        parent_post: List[Dict[str, Any]],
        parent_matrix: Dict[str, Any],
        processed_stages: dict  # 修改为字典，键为stage名称，值为stage信息
) -> List[Dict[str, Any]]:
    """
    当外层 stage 检测到 stages { ... } 块时，调用本函数：
    1. 从 nested_stages_content 中解析出所有的子 stage('xxx'){ ... }；
    2. 为每个子 stage 合并外层 stage 的 when、tools、env 等元信息；
    3. 返回这些嵌套子 stage 组成的列表。
    """
    sub_stages = []

    # 匹配每个 stages 内部的 stage
    stage_pattern = re.compile(r'stage\s*\(\s*[\'"](.+?)[\'"]\s*\)\s*\{', re.DOTALL)
    stage_matches = list(stage_pattern.finditer(nested_stages_content))

    for i, stage_match in enumerate(stage_matches):
        sub_stage_name = stage_match.group(1)

        # 如果已经处理过这个stage名称，则跳过
        if sub_stage_name in processed_stages:
            logger.info(f"嵌套stage已处理过: {sub_stage_name}")
            continue

        logger.info(f"处理嵌套stage: {sub_stage_name}")
        sub_stage_start = stage_match.end()

        # 逐字符匹配大括号，找到这个子 stage 的主体
        brace_count = 1
        pos = sub_stage_start
        while pos < len(nested_stages_content) and brace_count > 0:
            c = nested_stages_content[pos]
            if c == '{':
                brace_count += 1
            elif c == '}':
                brace_count -= 1
            pos += 1

        sub_stage_body = nested_stages_content[sub_stage_start:pos - 1].strip()
        logger.info(f"Nested sub_stage_body: {sub_stage_body}")

        # ---- 解析这个子 stage 内部的各种信息----
        tools_yaml = tool_to_yaml(sub_stage_body, "stage") or []
        post_yaml = post_to_yaml(sub_stage_body, [], "stage") or []
        env_yaml = environment_to_yaml(sub_stage_body, "stage") or {}
        option_yaml = option_to_yaml(sub_stage_body, "stage") or []
        matrix_yaml = convert_jenkins_matrix(sub_stage_body) or {}
        when_yaml = convert_jenkins_when_to_gha(sub_stage_body) or {}

        # ---- 合并外层 stage 的元信息到子 stage 中 ----
        final_when = merge_configs(parent_when, when_yaml)
        final_tools = merge_configs(parent_tools, tools_yaml)
        final_env = merge_configs(parent_env, env_yaml)
        final_options = merge_configs(parent_options, option_yaml)
        final_post = merge_configs(parent_post, post_yaml)
        final_matrix = merge_configs(parent_matrix, matrix_yaml)

        # 先检查这个子 stage 里是否存在嵌套的 stages { ... } 块
        nested_stages_block = extract_block(sub_stage_body, 'stages')
        if nested_stages_block:
            # 递归处理更深层嵌套
            logger.info(f"Detected nested stages block in stage '{sub_stage_name}', recursively parsing...")

            nested_sub_stages = _parse_stages_in_nested_block(
                nested_stages_block,
                parent_when=final_when,
                parent_tools=final_tools,
                parent_env=final_env,
                parent_options=final_options,
                parent_post=final_post,
                parent_matrix=final_matrix,
                processed_stages=processed_stages  # 传递已处理stage字典
            )
            sub_stages.extend(nested_sub_stages)
            continue

        # 检查这个子 stage 里是否存在 parallel { ... } 块
        parallel_block_content = extract_block(sub_stage_body, 'parallel')
        if parallel_block_content:
            # 递归处理并行子阶段
            logger.info(f"Detected parallel block in nested stage '{sub_stage_name}', parsing sub-stages...")

            parallel_sub_stages = _parse_stages_in_parallel_block(
                parallel_block_content,
                parent_when=final_when,
                parent_tools=final_tools,
                parent_env=final_env,
                parent_options=final_options,
                parent_post=final_post,
                parent_matrix=final_matrix,
                processed_stages=processed_stages  # 传递已处理stage字典
            )
            sub_stages.extend(parallel_sub_stages)
            continue

        # 普通 stage 处理
        steps_content = extract_block(sub_stage_body, 'steps')
        steps = parse_jenkins_steps(steps_content)

        # 创建stage信息
        stage_info = {
            'name': sub_stage_name,
            'steps': steps,
            'tools': final_tools,
            'post': final_post,
            'env': final_env,
            'option': final_options,
            'matrix': final_matrix,
            'when': final_when,
        }

        # 将stage信息保存到字典中，以后可以直接使用
        processed_stages[sub_stage_name] = stage_info
        sub_stages.append(stage_info)

    return sub_stages


def parse_stages_block(jenkinsfile_content: str) -> List[Dict[str, Any]]:
    """
    解析 Jenkinsfile.groovy 中的 stages 块，提取各个 stage 的信息。
    同时处理嵌套 stages 和 parallel 结构。
    """
    stages = []
    # 提取 stages 块
    stages_content = extract_block(jenkinsfile_content, 'stages')
    if not stages_content:
        logger.info("No stages block found in Jenkinsfile.groovy. ")
        return stages  # 没有 stages 定义

    # 匹配每个 stage
    stage_pattern = re.compile(r'stage\s*\(\s*[\'"](.+?)[\'"]\s*\)\s*\{', re.DOTALL)
    stage_matches = list(stage_pattern.finditer(stages_content))

    # 用于记录已经处理过的stage信息，键为stage名称，值为stage信息
    processed_stages = {}

    for i, stage_match in enumerate(stage_matches):
        stage_name = stage_match.group(1)

        # 如果当前stage名称已经被处理过，则跳过
        if stage_name in processed_stages:
            logger.info(f"stage_name: {stage_name} 已经处理过了")
            continue

        logger.info(f"处理顶层stage: {stage_name}")
        stage_start = stage_match.end()

        brace_count = 1
        pos = stage_start

        # 从 block_start 往后扫描, 找到与 stage('xxx') { 匹配的 "}"
        while pos < len(stages_content) and brace_count > 0:
            c = stages_content[pos]
            if c == '{':
                brace_count += 1
            elif c == '}':
                brace_count -= 1
            pos += 1

        stage_body = stages_content[stage_start: pos - 1].strip()
        logger.info(f"Current stage name = {stage_name}, body = {stage_body}")

        stages_match = re.search(r'^stages\s*\{', stage_body)
        parallel_match = re.search(r'^parallel\s*\{', stage_body)
        tools_yaml, post_yaml, env_yaml, option_yaml, matrix_yaml, when_yaml = [], [], {}, [], {}, {}
        if not stages_match and not parallel_match:
            # ---- 解析外层 stage 内的元信息 ----
            tools_yaml = tool_to_yaml(stage_body, "stage") or []
            post_yaml = post_to_yaml(stage_body, [], "stage") or []
            env_yaml = environment_to_yaml(stage_body, "stage") or {}
            option_yaml = option_to_yaml(stage_body, "stage") or []
            matrix_yaml = convert_jenkins_matrix(stage_body) or {}
            when_yaml = convert_jenkins_when_to_gha(stage_body) or {}

        # 检查是否有嵌套的 stages 块
        nested_stages_block = extract_block(stage_body, 'stages')
        if nested_stages_block:
            # 检测到嵌套 stages
            logger.info(f"Detected nested stages block in stage '{stage_name}', parsing sub-stages...")

            # 调用辅助函数，返回嵌套子 stage
            sub_stages = _parse_stages_in_nested_block(
                nested_stages_block,
                parent_when=when_yaml,
                parent_tools=tools_yaml,
                parent_env=env_yaml,
                parent_options=option_yaml,
                parent_post=post_yaml,
                parent_matrix=matrix_yaml,
                processed_stages=processed_stages  # 传递已处理stage字典
            )
            logger.info(f"Nested Sub_Stages: {sub_stages}")
            stages.extend(sub_stages)

            # 跳过外层 stage
            continue

        # 检查 parallel 块
        parallel_block_content = extract_block(stage_body, 'parallel')
        if parallel_block_content:
            logger.info(f"Detected parallel block in stage '{stage_name}', parsing sub-stages...")

            sub_stages = _parse_stages_in_parallel_block(
                parallel_block_content,
                parent_when=when_yaml,
                parent_tools=tools_yaml,
                parent_env=env_yaml,
                parent_options=option_yaml,
                parent_post=post_yaml,
                parent_matrix=matrix_yaml,
                processed_stages=processed_stages  # 传递已处理stage字典
            )
            logger.info(f"Parallel Sub_Stages: {sub_stages}")
            stages.extend(sub_stages)
            continue
        else:
            # 普通 stage 处理
            steps_content = extract_block(stage_body, 'steps')
            steps = parse_jenkins_steps(steps_content)

            # 创建stage信息
            stage_info = {
                'name': stage_name,
                'steps': steps,
                'tools': tools_yaml,
                'post': post_yaml,
                'env': env_yaml,
                'option': option_yaml,
                'matrix': matrix_yaml,
                'when': when_yaml
            }

            # 将stage信息保存到字典中，以后可以直接使用
            processed_stages[stage_name] = stage_info
            stages.append(stage_info)

    # 最后返回前移除任何重复项（基于名称判断）
    seen_stages = {}
    unique_stages = []
    for stage in stages:
        if stage['name'] not in seen_stages:
            seen_stages[stage['name']] = True
            unique_stages.append(stage)

    logger.info(f"处理完成，总共找到 {len(stages)} 个stages，去重后剩余 {len(unique_stages)} 个")
    return unique_stages


def stage_to_yaml(jenkinsfile_content: str, options_component, dependencies) -> Dict[str, Any]:
    stages = parse_stages_block(jenkinsfile_content)
    if not stages:
        logger.info("No stages found in Jenkinsfile.groovy.")
        return {}
    # 输出解析后的 stages
    logger.info("Parsed Stages:")
    for stage in stages:
        name = normalize_identifier(stage.get('name'))
        stage['name'] = name
        logger.info(stage)

    # 加载插件
    logger.info("准备加载plugin！")
    plugins = load_plugins('plugins')
    logger.info("成功加载plugin！")
    if not plugins:
        logger.warning("No plugins loaded. All steps will use the llm converter.")
    # 初始化转换器
    converter = GitHubActionsConverter(plugins)
    github_actions_yaml_dict = converter.generate_yaml(stages, options_component, dependencies)
    if parse_environment.GITHUB_PATH_VALUE and 'jobs' in github_actions_yaml_dict:
        for job in github_actions_yaml_dict['jobs']:
            if 'steps' in github_actions_yaml_dict['jobs'][job]:
                github_actions_yaml_dict['jobs'][job]['steps'].insert(0, {"name": "Set PATH environment", "run": f'echo "{parse_environment.GITHUB_PATH_VALUE}" >> $GITHUB_PATH'})
    return github_actions_yaml_dict

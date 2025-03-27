import re

from ruamel.yaml import YAML, CommentedMap
from ruamel.yaml.scalarstring import PlainScalarString
from typing import Dict, Any, Optional, List
import copy
from converter.utils.getLogger import setup_logging

# 设置日志
logger = setup_logging()


def reorder_job_fields(job_config: Dict[str, Any]) -> CommentedMap:
    """
    按照指定顺序重新排序job的字段

    Args:
        job_config: 原始job配置

    Returns:
        重新排序后的job配置
    """
    # 定义字段优先级顺序
    field_order = ['name', 'runs-on', 'needs', 'if']

    # 创建一个新的有序字典
    ordered_job = CommentedMap()

    # 首先按指定顺序添加优先字段(不包括steps)
    for field in field_order:
        if field in job_config:
            ordered_job[field] = job_config[field]

    # 然后添加其他字段(除了steps)
    for field, value in job_config.items():
        if field not in field_order and field != 'steps':
            ordered_job[field] = value

    # 最后添加steps字段(如果存在)
    if 'steps' in job_config:
        ordered_job['steps'] = job_config['steps']

    return ordered_job


def needs_checkout(job_def: dict) -> bool:
    """
    判断给定的 job 定义是否需要执行 actions/checkout。
    返回 True 表示需要；False 表示不需要。
    """
    if "steps" not in job_def or not job_def["steps"]:
        return False

    # 1. 检查是否已有 checkout action
    for step in job_def["steps"]:
        if isinstance(step, dict) and "uses" in step:
            uses_val = str(step["uses"]).lower()
            if "actions/checkout" in uses_val:
                return False  # 已经有 checkout，不需要再添加

    # 2. 基于 job 名称判断
    if "name" in job_def:
        job_name = str(job_def["name"]).lower()
        build_related_job_names = [
            "build", "compile", "test", "lint", "check", "analyze",
            "deploy", "publish", "package", "bundle"
        ]
        for term in build_related_job_names:
            if term in job_name:
                return True

    # 3. 检查 steps 中是否有依赖源码的操作
    build_related_commands = [
        # 基本构建工具
        r"\bmake\b", r"\bnpm\b", r"\byarn\b", r"\bpython\b", r"\bpip\b",
        r"\bgradle\b", r"\bmvn\b", r"\bsbt\b", r"\bcargo\b", r"\bgcc\b",
        r"\bg\+\+\b", r"\bjavac\b", r"\bkotlinc\b", r"\bgo\b", r"\bdotnet\b",

        # 测试框架
        r"\bjest\b", r"\bmocha\b", r"\bpytest\b", r"\bjunit\b", r"\brspec\b",

        # 文件操作
        r"\bgit\b", r"\bfind\b", r"\bgrep\b", r"\bcat\b", r"\bls\b",
        r"\bcp\b", r"\bmv\b", r"\brm\b"
    ]

    # 文件路径和扩展名模式
    file_path_patterns = [
        r"\./", r"\.\.", r"/\w+/",  # 常见路径表示法
        r"src/", r"dist/", r"build/", r"public/",  # 常见目录名
        r"\.(js|ts|py|java|c|cpp|go|rb|php|sh|yaml|json|html|css|md|txt)\b"  # 常见文件扩展名
    ]

    # 环境变量模式
    env_var_patterns = [r"\$GITHUB_WORKSPACE", r"\$\{GITHUB_WORKSPACE\}"]

    for step in job_def["steps"]:
        if isinstance(step, dict) and "run" in step:
            command_line = str(step["run"])

            # 检查构建命令
            for pattern in build_related_commands:
                if re.search(pattern, command_line, re.IGNORECASE):
                    return True

            # 检查文件路径
            for pattern in file_path_patterns:
                if re.search(pattern, command_line):
                    return True

            # 检查环境变量
            for pattern in env_var_patterns:
                if re.search(pattern, command_line):
                    return True

        # 检查 uses 中可能需要源码的 action
        if isinstance(step, dict) and "uses" in step:
            uses_val = str(step["uses"]).lower()
            code_dependent_actions = ["lint", "test", "build", "compile", "scan"]
            for term in code_dependent_actions:
                if term in uses_val:
                    return True

    return False


def merge_yaml_components(components: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    合并多个YAML组件字典为一个完整的GitHub Actions工作流配置

    Args:
        components: 包含各个YAML组件字典的列表

    Returns:
        合并后的完整GitHub Actions工作流字典
    """
    # 创建基础结构 - 将env放在on后面，jobs前面
    result = {
        PlainScalarString('name'): 'Converted Workflow',
        PlainScalarString('on'):
            {
                'push': {
                    'branches': ['main']
                },
                'pull_request': {
                    'branches': ['main']
                }
            },
        PlainScalarString('env'): {},  # 添加空的env部分，位置在on后，jobs前
        PlainScalarString('jobs'): {}
    }

    # 遍历所有组件进行合并
    for component in components:
        if not component:  # 跳过空组件
            continue

        # 处理触发器 ('on')
        if 'on' in component:
            for trigger, config in component['on'].items():
                if trigger not in result['on']:
                    result['on'][trigger] = copy.deepcopy(config)
                else:
                    # 合并已存在的触发器配置
                    for key, value in config.items():
                        if key not in result['on'][trigger]:
                            result['on'][trigger][key] = copy.deepcopy(value)
                        elif key == 'inputs' and isinstance(value, dict):
                            # 合并workflow_dispatch的inputs
                            for input_name, input_config in value.items():
                                result['on'][trigger]['inputs'][input_name] = copy.deepcopy(input_config)

        # 处理环境变量
        if 'env' in component:
            # 全局环境变量
            for env_name, env_value in component['env'].items():
                result['env'][env_name] = env_value

        # 处理jobs
        if 'jobs' in component:
            logger.info(f"Processing jobs in component, found {len(component['jobs'])} jobs")
            for job_id, job_config in component['jobs'].items():
                logger.info(f"Processing job '{job_id}'")
                # 检查job是否有步骤，如果steps为空或不存在，跳过此job
                if 'steps' not in job_config or len(job_config['steps']) == 0:
                    logger.warning(f"Job '{job_id}' has no steps, skipping")
                    continue

                if job_id not in result['jobs']:
                    logger.info(f"Adding new job '{job_id}' to result")
                    # 直接复制整个任务配置
                    result['jobs'][job_id] = copy.deepcopy(job_config)

                    # 为每个job单独判断是否需要checkout
                    needs_checkout_result = needs_checkout(job_config)
                    logger.info(f"Job '{job_id}' needs checkout: {needs_checkout_result}")
                    if needs_checkout_result:
                        logger.info(f"Adding checkout step to job '{job_id}'")
                        # 直接添加checkout步骤，needs_checkout()已经确保没有现有的checkout
                        checkout_step = {'uses': 'actions/checkout@v3'}
                        result['jobs'][job_id]['steps'].insert(0, checkout_step)
                        logger.debug(f"Checkout step added to job '{job_id}'")
                    # # 如果需要添加checkout步骤，并且job有steps
                    # if add_checkout_step and 'steps' in job_config:
                    #     # 检查job中是否已经有checkout步骤
                    #     has_checkout = False
                    #     for step in job_config.get('steps', []):
                    #         # 检查是否有使用actions/checkout的步骤
                    #         if 'uses' in step and step['uses'].startswith('actions/checkout@'):
                    #             has_checkout = True
                    #             break
                    #
                    #     # 如果没有找到checkout步骤，则添加
                    #     if not has_checkout:
                    #         # 在steps开头添加checkout步骤
                    #         checkout_step = {'uses': 'actions/checkout@v3'}
                    #         result['jobs'][job_id]['steps'].insert(0, checkout_step)
                    #         add_checkout_step = False  # 只添加一次
                else:
                    logger.info(f"Job '{job_id}' already exists, merging configurations")
                    # 已存在同名的任务，需要合并配置
                    for key, value in job_config.items():
                        if key not in result['jobs'][job_id]:
                            logger.debug(f"Adding new property '{key}' to existing job '{job_id}'")
                            result['jobs'][job_id][key] = copy.deepcopy(value)
                        elif key == 'steps' and isinstance(value, list):
                            # 合并steps
                            logger.debug(f"Extending steps for job '{job_id}' with {len(value)} new steps")
                            result['jobs'][job_id]['steps'].extend(copy.deepcopy(value))

        # 处理steps (如果没有jobs但直接有steps)
        elif 'steps' in component:
            logger.info(f"Component has direct steps without jobs, found {len(component['steps'])} steps")
            # 如果没有预定义的job，创建一个默认的build job
            if 'default-job' not in result['jobs']:
                logger.info("Creating default 'default-job' job")
                result['jobs']['default-job'] = {
                    'runs-on': 'ubuntu-latest',
                    'steps': []
                }

                # 添加checkout步骤
                # 检查默认job是否需要checkout，如果需要则添加
                needs_checkout_result = needs_checkout(result['jobs']['default-job'])
                logger.info(f"Default job 'default-job' needs checkout: {needs_checkout_result}")
                if needs_checkout_result:
                    logger.info("Adding checkout step to default 'default-job' job")
                    result['jobs']['default-job']['steps'].append({'uses': 'actions/checkout@v3'})
                    logger.debug("Checkout step added to default job")
                    # add_checkout_step = False

            logger.info(f"Adding {len(component['steps'])} steps to 'default-job' job")
            # 添加steps
            result['jobs']['default-job']['steps'].extend(copy.deepcopy(component['steps']))

        # 处理其他顶级配置
        for key, value in component.items():
            if key not in ['on', 'env', 'steps', 'jobs']:
                result[PlainScalarString(key)] = copy.deepcopy(value)

    # 如果没有触发器，添加默认的push触发器
    if not result['on']:
        result['on'] = {
            'push': {
                'branches': ['main']
            }
        }

    # 如果env为空，移除它
    if not result['env']:
        del result['env']

    # 如果没有任何job，添加默认的build job
    if not result['jobs']:
        result['jobs'] = {
            'build': {
                'runs-on': 'ubuntu-latest',
                'steps': [
                    {
                        'uses': 'actions/checkout@v3'
                    }
                ]
            }
        }

    # 重新排序每个job的字段，确保按照指定的顺序
    ordered_jobs = CommentedMap()
    for job_id, job_config in result['jobs'].items():
        ordered_jobs[job_id] = reorder_job_fields(job_config)

    # 替换原有的jobs
    result['jobs'] = ordered_jobs

    return result
import re
import traceback
from concurrent.futures import ThreadPoolExecutor
import time
from typing import List, Dict, Any
from jinja2 import Environment, FileSystemLoader
from ruamel.yaml.scalarstring import PlainScalarString
from ruamel.yaml import YAML
from converter.plugins.base_plugin import BasePlugin
from converter.utils.JenkinsComparisonSingle import JenkinsComparisonSingle
from converter.utils.getLogger import setup_logging
from ruamel.yaml.comments import CommentedSeq, CommentedMap
from converter.rag_llm_generator.rag_llm_generator import generate_github_actions
import json

from converter.utils.yaml_to_string import yaml_to_string

logger = setup_logging()


class GitHubActionsConverter:
    def __init__(self, plugins: Dict[str, BasePlugin]):
        self.plugins = plugins
        self.env = Environment(
            trim_blocks=True,
            lstrip_blocks=True
        )

    # def convert_steps(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    #     """
    #     将 Jenkins 步骤转换为 GitHub Actions 步骤，使用插件转换器。
    #     """
    #     converted_steps = CommentedSeq()
    #
    #     for step in steps:
    #         step_name = step.get('name')
    #         raw_args = step.get('raw_args', '')
    #         # 尝试使用插件解析和转换步骤
    #         handled = False
    #         for plugin_name, plugin in self.plugins.items():
    #             if plugin.can_handle(step):
    #                 # 解析参数
    #                 parsed_args = plugin.parse_args(raw_args)
    #                 logger.debug(f"Parsed args for step '{step_name}': {parsed_args}")
    #                 step['args'] = parsed_args
    #                 # 转换步骤
    #                 plugin_converted_steps = plugin.convert(step)
    #                 handled = True
    #                 logger.info(f"Step '{step_name}' handled by plugin '{plugin_name}'.")
    #                 logger.debug(f"Converted steps: {plugin_converted_steps}")
    #                 # 添加插件转换的步骤
    #                 converted_steps.extend(plugin_converted_steps)
    #                 break
    #
    #         if not handled:
    #
    #             logger.info(f"Step '{step_name}' or '{step}' will be handled by LLM.")
    #             logger.info(
    #                 f"Step '{step}': \n# TODO:This section is pending transformation from Jenkinsfile to GitHub "
    #                 f"Actions YAML.")
    #
    #             # 1) 调用大模型
    #             generate_via_llm = generate_github_actions(step)
    #             # logger.info(f"Raw LLM output: '{generate_via_llm}'")
    #
    #             # 2) 预先清理
    #             cleaned_output = sanitize_llm_output(generate_via_llm)
    #
    #             # 3) 解析 JSON
    #             try:
    #                 parsed_steps = json.loads(cleaned_output)  # 期望是一个列表
    #                 # 如果返回的是单个对象，可以在这里加判定
    #                 if not isinstance(parsed_steps, list):
    #                     # 若模型只返回一个对象，也可包装成 list
    #                     parsed_steps = [parsed_steps]
    #                 # 添加步骤到序列
    #                 converted_steps.extend(parsed_steps)
    #             except json.JSONDecodeError as e:
    #                 logger.warning(f"Failed to parse LLM output as JSON: {e}")
    #                 converted_step = CommentedMap()
    #                 converted_step['name'] = step_name
    #                 converted_step['raw_args'] = raw_args
    #                 # 添加步骤到序列
    #                 converted_steps.extend(converted_step)
    #
    #             # 为最后添加的项设置注释
    #             if step_name is not None:
    #                 converted_steps.yaml_set_comment_before_after_key(
    #                     len(converted_steps) - 1,
    #                     before=f"TODO: The step '{step_name}' is implemented via LLM and requires further integration and validation.",
    #                     indent=6
    #                 )
    #             else:
    #                 converted_steps.yaml_set_comment_before_after_key(
    #                     len(converted_steps) - 1,
    #                     before=f"TODO: The step '{step}' is implemented via LLM and requires further integration and "
    #                            f"validation.",
    #                     indent=6
    #                 )
    #
    #     return converted_steps
    def convert_steps(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        将 Jenkins 步骤转换为 GitHub Actions 步骤，使用插件转换器和并行LLM处理。
        """
        if not steps:
            return CommentedSeq()

        logger.info(f"开始转换 {len(steps)} 个 Jenkins 步骤到 GitHub Actions")
        start_time = time.time()

        # 存储所有步骤的转换结果和原始位置
        all_steps_results = []
        llm_tasks = []  # 存储需要LLM处理的任务
        plugin_handled_count = 0

        # 第一次遍历：处理插件能处理的步骤，收集需要LLM处理的步骤
        logger.info(f"开始处理插件能处理的步骤")
        for i, step in enumerate(steps):
            step_name = step.get('name')
            raw_args = step.get('raw_args', '')
            # 尝试使用插件解析和转换步骤
            handled = False
            for plugin_name, plugin in self.plugins.items():
                if plugin.can_handle(step):
                    # 解析参数
                    parsed_args = plugin.parse_args(raw_args)
                    logger.debug(f"Parsed args for step '{step_name}': {parsed_args}")
                    step['args'] = parsed_args
                    # 转换步骤
                    plugin_converted_steps = plugin.convert(step)
                    handled = True
                    logger.info(f"Step '{step_name}' handled by plugin '{plugin_name}'.")
                    logger.debug(f"Converted steps: {plugin_converted_steps}")
                    # 保存插件转换的步骤和原始位置
                    all_steps_results.append((i, plugin_converted_steps, step_name, None))
                    plugin_handled_count += 1
                    break

            if not handled:
                # 收集需要LLM处理的步骤，保存索引和步骤信息
                logger.info(f"Step '{step_name}' or '{step}' will be handled by LLM.")
                llm_tasks.append((i, step))

        logger.info(f"插件成功处理了 {plugin_handled_count} 个步骤，{len(llm_tasks)} 个步骤需要 LLM 处理")

        # 使用线程池并行处理LLM转换任务
        if llm_tasks:
            logger.info(f"开始并行处理 {len(llm_tasks)} 个需要 LLM 转换的步骤")
            llm_start_time = time.time()

            def process_llm_step(task_info):
                idx, step = task_info
                step_name = step.get('name')
                raw_args = step.get('raw_args', '')

                # 调用大模型
                logger.info(f"使用 LLM 处理步骤 '{step_name}'")
                try:
                    generate_via_llm = generate_github_actions(step)
                    logger.debug(f"LLM 原始输出: {generate_via_llm[:100]}..." if len(
                        generate_via_llm) > 100 else generate_via_llm)

                    # 预先清理
                    cleaned_output = sanitize_llm_output(generate_via_llm)
                    logger.debug(
                        f"清理后的输出: {cleaned_output[:100]}..." if len(cleaned_output) > 100 else cleaned_output)

                    try:
                        # 解析JSON
                        parsed_steps = json.loads(cleaned_output)
                        if not isinstance(parsed_steps, list):
                            parsed_steps = [parsed_steps]

                        # 返回原始索引、解析后的步骤和步骤名称（用于注释）
                        return (idx, parsed_steps, step_name, step)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse LLM output as JSON: {e}")
                        logger.warning(f"LLM 输出无法解析为 JSON，将使用简单的替代步骤: {cleaned_output[:200]}")
                        converted_step = CommentedMap()
                        converted_step['name'] = step_name
                        converted_step['raw_args'] = raw_args
                        return (idx, [converted_step], step_name, step)
                except Exception as e:
                    logger.error(f"处理 LLM 步骤时发生错误: {str(e)}")
                    converted_step = CommentedMap()
                    converted_step['name'] = f"Error processing step: {step_name}"
                    converted_step['run'] = f"echo 'Error occurred during conversion: {str(e)}'"
                    return (idx, [converted_step], step_name, step)

            # 使用线程池并行处理
            llm_results = []
            with ThreadPoolExecutor(max_workers=min(5, len(llm_tasks))) as executor:
                # 提交所有任务
                futures = [executor.submit(process_llm_step, task) for task in llm_tasks]

                # 收集结果
                for future in futures:
                    try:
                        llm_results.append(future.result())
                    except Exception as e:
                        logger.error(f"处理 LLM 任务时发生错误: {str(e)}")

            # 添加LLM处理结果到总结果列表
            all_steps_results.extend(llm_results)

            llm_end_time = time.time()
            logger.info(f"Steps: LLM 并行处理完成，耗时: {llm_end_time - llm_start_time:.2f} 秒")

        # 按原始位置排序所有结果
        all_steps_results.sort(key=lambda x: x[0])

        # 创建最终的转换步骤序列
        converted_steps = CommentedSeq()

        # 将所有结果添加到converted_steps，保持原始顺序
        for _, parsed_steps, step_name, original_step in all_steps_results:
            # 获取当前长度作为添加位置
            current_position = len(converted_steps)

            # 添加步骤
            converted_steps.extend(parsed_steps)

            # 为LLM处理的步骤添加注释
            if original_step is not None:  # 仅对LLM处理的步骤添加注释
                if step_name is not None:
                    converted_steps.yaml_set_comment_before_after_key(
                        current_position,
                        before=f"TODO: The step '{step_name}' is implemented via LLM and requires further integration and validation.",
                        indent=6
                    )
                else:
                    converted_steps.yaml_set_comment_before_after_key(
                        current_position,
                        before=f"TODO: The step '{original_step}' is implemented via LLM and requires further integration and validation.",
                        indent=6
                    )

        end_time = time.time()
        total_steps = plugin_handled_count + len(llm_tasks)
        logger.info(f"转换完成: 总共 {total_steps} 个 GitHub Actions 步骤，总耗时: {end_time - start_time:.2f} 秒")
        logger.info(f"转换统计: {plugin_handled_count} 个由插件处理，{len(llm_tasks)} 个由 LLM 处理")

        return converted_steps

    # def generate_yaml(self, stages: List[Dict[str, Any]], option_component, dependencies) -> Dict[str, Any]:
    #     """
    #     生成 GitHub Actions 的 stages 字典。
    #     :param stages: Jenkins 阶段列表
    #     :param option_component: 全局 option
    #     :param dependencies: 阶段依赖关系字典，格式为 {stage_name: [dependency_stages]}
    #     """
    #     jobs = {}
    #     jenkins_comparison = JenkinsComparisonSingle()
    #     for stage in stages:
    #         # 生成 job 名称，转换为小写并用下划线替换空格
    #         job_name = re.sub(r'\s+', '_', stage['name']).lower()
    #         stage_name = stage['name']  # 保存原始阶段名称，用于查找依赖关系
    #         steps = self.convert_steps(stage['steps'])
    #
    #         # 创建job基础配置，按照期望的顺序添加键
    #         job_config = {}
    #
    #         # 处理依赖关系，添加 needs 字段
    #         if dependencies and stage_name in dependencies and dependencies[stage_name]:
    #             # 将依赖的阶段名称转换为 job 名称的格式（小写+下划线）
    #             needs_list = [re.sub(r'\s+', '_', dep).lower() for dep in dependencies[stage_name]]
    #             if needs_list:  # 只有在有依赖时才添加 needs 字段
    #                 job_config['needs'] = needs_list
    #                 logger.info(f"Added dependencies for {job_name}: {needs_list}")
    #
    #         # 处理 when 条件
    #         if stage.get('when'):
    #             # 当 when 是字典类型时，直接添加 if 条件
    #             if isinstance(stage['when'], dict) and 'if' in stage['when']:
    #                 job_config['if'] = stage['when']['if']
    #             # 当 when 是非空列表时，处理列表中的条件
    #             elif isinstance(stage['when'], list) and stage['when']:
    #                 # 如果列表中有字典元素且包含 if 键
    #                 for item in stage['when']:
    #                     if isinstance(item, dict) and 'if' in item:
    #                         job_config['if'] = item['if']
    #                         break
    #
    #         # 添加运行环境配置（保持在 if 条件之后）
    #         job_config['runs-on'] = 'ubuntu-latest'
    #         # 添加matrix到job配置中
    #         if stage['matrix']:
    #             logger.info(f"Matrix: {stage['matrix']}")
    #             # 确保strategy键存在
    #             if 'strategy' not in job_config:
    #                 job_config['strategy'] = {}
    #             # 将matrix添加到strategy中
    #             if 'matrix' in stage['matrix']['strategy']:
    #                 job_config['strategy']['matrix'] = stage['matrix']['strategy']['matrix']
    #
    #         # 添加options到job配置中
    #         # 如果有全局option:
    #         if option_component:
    #             logger.info(f"有全局option: {option_component}")
    #             # 遍历全局option每个配置项
    #             for option_key, option_value in option_component.items():
    #                 if option_key == 'strategy' and 'strategy' in job_config:
    #                     # 合并strategy而不是覆盖
    #                     for strategy_key, strategy_value in option_value.items():
    #                         job_config['strategy'][strategy_key] = strategy_value
    #                 else:
    #                     job_config[option_key] = option_value
    #         else:
    #             logger.info(f"无全局option!")
    #         # 如果有单个job的option：
    #         if stage['option']:
    #             # 遍历options中的每个配置项，添加到job_config
    #             for option_key, option_value in stage['option'].items():
    #                 job_config[option_key] = option_value
    #         # 添加环境变量到job配置中
    #         if stage['env']:
    #             job_config['env'] = stage['env']
    #
    #         # 添加steps（在options之后）
    #         job_config['steps'] = stage['tools'] + steps + stage['post']
    #         jobs[job_name] = job_config
    #
    #         jenkins_block_name = "stage('" + stage_name + "')"
    #
    #         jenkins_comparison.add_comparison(yaml_to_string({job_name: job_config}), jenkins_block_name, "stage")
    #     yaml_content = {
    #         PlainScalarString('jobs'): jobs
    #     }
    #
    #     logger.debug(f"Generated YAML content: {yaml_content}")
    #
    #     return yaml_content
    def generate_yaml(self, stages: List[Dict[str, Any]], option_component, dependencies) -> Dict[str, Any]:
        """
        生成 GitHub Actions 的 stages 字典。
        :param stages: Jenkins 阶段列表
        :param option_component: 全局 option
        :param dependencies: 阶段依赖关系字典，格式为 {stage_name: [dependency_stages]}
        """
        logger.info(f"开始生成 GitHub Actions YAML，总共 {len(stages)} 个 stages")
        start_time = time.time()

        # 存储所有 job 的结果
        jobs = {}
        jenkins_comparison = JenkinsComparisonSingle()

        # 定义处理单个 stage 的函数
        def process_stage(stage):
            stage_start_time = time.time()
            logger.info(f"开始处理 stage: {stage['name']}")

            # 生成 job 名称，转换为小写并用下划线替换空格
            job_name = re.sub(r'\s+', '_', stage['name']).lower()
            stage_name = stage['name']  # 保存原始阶段名称，用于查找依赖关系

            # 转换 steps（这里 convert_steps 已经是并行处理的）
            steps = self.convert_steps(stage['steps'])

            # 创建job基础配置，按照期望的顺序添加键
            job_config = {}

            # 处理依赖关系，添加 needs 字段
            if dependencies and stage_name in dependencies and dependencies[stage_name]:
                # 将依赖的阶段名称转换为 job 名称的格式（小写+下划线）
                needs_list = [re.sub(r'\s+', '_', dep).lower() for dep in dependencies[stage_name]]
                if needs_list:  # 只有在有依赖时才添加 needs 字段
                    job_config['needs'] = needs_list
                    logger.info(f"Added dependencies for {job_name}: {needs_list}")

            # 处理 when 条件
            if stage.get('when'):
                # 当 when 是字典类型时，直接添加 if 条件
                if isinstance(stage['when'], dict) and 'if' in stage['when']:
                    job_config['if'] = stage['when']['if']
                # 当 when 是非空列表时，处理列表中的条件
                elif isinstance(stage['when'], list) and stage['when']:
                    # 如果列表中有字典元素且包含 if 键
                    for item in stage['when']:
                        if isinstance(item, dict) and 'if' in item:
                            job_config['if'] = item['if']
                            break

            # 添加运行环境配置（保持在 if 条件之后）
            job_config['runs-on'] = 'ubuntu-latest'

            # 添加matrix到job配置中
            if stage['matrix']:
                logger.info(f"Matrix: {stage['matrix']}")
                # 确保strategy键存在
                if 'strategy' not in job_config:
                    job_config['strategy'] = {}
                # 将matrix添加到strategy中
                if 'matrix' in stage['matrix']['strategy']:
                    job_config['strategy']['matrix'] = stage['matrix']['strategy']['matrix']

            # 添加options到job配置中
            # 如果有全局option:
            if option_component:
                logger.info(f"有全局option: {option_component}")
                # 遍历全局option每个配置项
                for option_key, option_value in option_component.items():
                    if option_key == 'strategy' and 'strategy' in job_config:
                        # 合并strategy而不是覆盖
                        for strategy_key, strategy_value in option_value.items():
                            job_config['strategy'][strategy_key] = strategy_value
                    else:
                        job_config[option_key] = option_value
            else:
                logger.info(f"无全局option!")

            # 如果有单个job的option：
            if stage['option']:
                # 遍历options中的每个配置项，添加到job_config
                for option_key, option_value in stage['option'].items():
                    job_config[option_key] = option_value

            # 添加环境变量到job配置中
            if stage['env']:
                job_config['env'] = stage['env']

            # 添加steps（在options之后）
            job_config['steps'] = stage['tools'] + steps + stage['post']

            jenkins_block_name = "stage('" + stage_name + "')"
            comparison_result = yaml_to_string({job_name: job_config})

            stage_end_time = time.time()
            logger.info(f"Stage '{stage_name}' 处理完成，耗时: {stage_end_time - stage_start_time:.2f} 秒")

            # 返回处理结果
            return job_name, job_config, jenkins_block_name, comparison_result

        # 使用线程池并行处理所有 stages
        results = []
        with ThreadPoolExecutor(max_workers=min(10, len(stages))) as executor:
            # 提交所有 stage 处理任务
            futures = [executor.submit(process_stage, stage) for stage in stages]

            # 收集结果
            for future in futures:
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.error(f"处理 stage 时发生错误: {str(e)}")
                    traceback.print_exc()

        # 处理收集到的结果
        for job_name, job_config, jenkins_block_name, comparison_result in results:
            jobs[job_name] = job_config
            # 添加到比较器中
            jenkins_comparison.add_comparison(comparison_result, jenkins_block_name, "stage")

        yaml_content = {
            PlainScalarString('jobs'): jobs
        }

        end_time = time.time()
        logger.info(f"GitHub Actions YAML 生成完成，总共 {len(jobs)} 个 jobs，总耗时: {end_time - start_time:.2f} 秒")
        logger.debug(f"Generated YAML content: {yaml_content}")

        return yaml_content


def sanitize_llm_output(llm_text: str) -> str:
    """
    清理大模型返回的字符串，去掉可能的Markdown代码块标记等。
    也可在里面做其他简单的正则清洗。
    """
    # 去掉Markdown式的```json ... ```包裹
    # 注意：此处是一个简单示例，可能需要更健壮的正则
    llm_text = re.sub(r'```(?:json)?(.*?)```', r'\1', llm_text, flags=re.DOTALL)
    return llm_text.strip()

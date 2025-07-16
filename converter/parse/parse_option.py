import json
import re
import os
from dotenv import load_dotenv
from openai import OpenAI
from ruamel.yaml import YAML
from typing import Dict, Any

from converter.utils.JenkinsComparisonSingle import JenkinsComparisonSingle
from converter.utils.extract_block_by_scope import extract_block_by_scope
from converter.utils.extract_complete_block import extract_complete_block_with_normalized_indentation
from converter.utils.getLogger import setup_logging
from converter.utils.yaml_to_string import yaml_to_string

# 设置日志
logger = setup_logging()

load_dotenv()

def construct_system_prompt() -> str:
    system_instructions = (
        "You are a senior CI/CD engineer tasked with converting Jenkins options to GitHub Actions. "
        "Think step by step to ensure accurate conversion.\n\n"

        "Conversion Rules:\n"
        "1. timeout(time, unit):\n"
        "   - HOURS → timeout-minutes: time*60\n"
        "   - MINUTES → timeout-minutes: time\n"
        "2. retry(n):\n"
        "   → strategy.retry.max: n\n"
        "3. skipDefaultCheckout():\n"
        "   → steps: disable default checkout + add custom checkout\n"
        "4. quietPeriod(n):\n"
        "   → steps: add 'sleep n' step\n"
        "5. buildDiscarder(...):\n"
        "   → notes: add repository retention instructions\n"
        "6. preserveStashes(...):\n"
        "   → steps: add actions/upload-artifact\n\n"

        "Output Requirements:\n"
        "- Return JSON with this structure:\n"
        "  {\n"
        "    \"timeout-minutes\": int | null,\n"
        "    \"strategy\": {\"retry\": {\"max\": int} | null},\n"
        "    \"steps\": [\n"
        "      {\"name\": str, \"uses\": str, \"run\": str, ...}  # GitHub Actions steps\n"
        "    ],\n"
        "    \"notes\": [str]       # Human-readable guidance\n"
        "  }\n"
        "- Keys must match GitHub Actions schema exactly\n"
        "- If a key does not have a value, just leave it out, don't use null in the output\n"
        "- Include BOTH code and guidance for complex conversions\n"
        "- Never use markdown or non-JSON content"
    )
    return system_instructions


def construct_prompt(jenkins_options):
    """
    构建发送给大模型的提示内容
    :param jenkins_options: Jenkins options 字典（例如 {'timeout': {...}, 'retry': 3}）
    """
    prompt = (
        "### Jenkins Options Configuration:\n"
        f"{json.dumps(jenkins_options, indent=2)}\n"
        "Please convert these Jenkins options to GitHub Actions YAML configuration.\n"
        "Remember to return the result **strictly** as valid JSON.\n"
    )
    return prompt


def parse_options_block(content: str, scope="global") -> Dict[str, Any]:
    """
    增强版 Jenkins options 解析器
    支持嵌套结构如 buildDiscarder(logRotator(numToKeepStr: '10'))
    """
    options_dict = {}

    # 使用通用函数提取environment块内容
    options_content = extract_block_by_scope(content, 'options', scope)

    if not options_content:
        return options_dict

    logger.info(f"Options_content [{scope}]: {options_content}")

    # 增强的分割逻辑：按分号或换行分割，忽略括号内的分隔符
    option_lines = re.split(r'[\n;]+(?![^()]*\))', options_content)

    for line in option_lines:
        line = line.strip()
        if not line:
            continue

        # 解析选项名称和参数（支持多级嵌套）
        option_match = re.match(
            r'(\w+)'  # 选项名称（如 timeout）
            r'\(\s*(.*?)\s*\)',  # 参数部分（支持嵌套）
            line, re.DOTALL
        )
        if not option_match:
            continue

        key = option_match.group(1)
        params_str = option_match.group(2)
        params = parse_parameters(params_str)  # 增强的参数解析

        options_dict[key] = params

    logger.info(f"Options Parsed:: {options_dict}")
    return options_dict


def parse_parameters(param_str: str) -> Any:
    """
    递归解析参数，支持嵌套结构如 logRotator(numToKeepStr: '10')
    """
    if not param_str:
        return {}

    # 分割顶层参数（忽略嵌套逗号）
    param_list = split_top_level_params(param_str)
    params = {}

    for param in param_list:
        # 处理键值对（如 time:1 或 logRotator(...)）
        if ':' in param:
            key, value = split_key_value(param)
            params[key.strip()] = parse_value(value.strip())
        # 处理无值参数（如 true/false）
        else:
            return parse_primitive_value(param.strip())

    return params


def split_top_level_params(s: str) -> list:
    """
    分割顶层参数，忽略嵌套括号内的逗号
    示例输入: "time:1, logRotator(numToKeep:5, daysToKeep:7)"
    输出: ["time:1", "logRotator(numToKeep:5, daysToKeep:7)"]
    """
    params = []
    current = []
    bracket_depth = 0

    for char in s:
        if char == '(':
            bracket_depth += 1
        elif char == ')':
            bracket_depth -= 1
        elif char == ',' and bracket_depth == 0:
            params.append(''.join(current).strip())
            current = []
            continue
        current.append(char)

    if current:
        params.append(''.join(current).strip())

    return params


def split_key_value(s: str) -> tuple:
    """
    分割键值对，处理可能的嵌套结构
    示例输入: "logRotator(numToKeep:5)"
    输出: ("logRotator", "numToKeep:5")
    """
    key = []
    value = []
    colon_found = False
    bracket_depth = 0

    for char in s:
        if not colon_found and char == ':':
            colon_found = True
            continue
        if not colon_found:
            key.append(char)
        else:
            value.append(char)

    return ''.join(key).strip(), ''.join(value).strip()


def parse_value(value: str) -> Any:
    """
    递归解析值（支持嵌套函数调用）
    """
    # 检测函数调用（如 logRotator(...)）
    func_match = re.match(r'^(\w+)\((.*)\)$', value, re.DOTALL)
    if func_match:
        func_name = func_match.group(1)
        func_params = parse_parameters(func_match.group(2))
        return {func_name: func_params}

    # 基本类型解析
    return parse_primitive_value(value)


def parse_primitive_value(value: str) -> Any:
    """
    解析基本类型值：字符串、数字、布尔值
    """
    # 去除包围的引号
    if (value.startswith("'") and value.endswith("'")) or \
            (value.startswith('"') and value.endswith('"')):
        return value[1:-1]

    # 布尔值
    if value.lower() in ['true', 'false']:
        return value.lower() == 'true'

    # 数字
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            pass

    # 无法解析则返回原始字符串
    return value


def generate_yaml(options: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 Jenkins 的 options 转换为 GitHub Actions 的 YAML 格式
    支持自动识别 timeout/retry，并为其他配置项提供扩展接口
    """
    github_actions_job = {}

    # 存储未识别的配置项
    unrecognized_options = []

    # 动态解析每个 option 项
    for option_name, option_params in options.items():
        # 已支持的配置项处理
        if option_name == "timeout":
            handle_timeout(github_actions_job, option_params)
        elif option_name == "retry":
            handle_retry(github_actions_job, option_params)
        elif option_name == "buildDiscarder":
            handle_build_discarder(github_actions_job, option_params)
        else:
            # 记录未识别的配置项（可扩展）
            unrecognized_options.append((option_name, option_params))

    # 添加扩展处理接口（示例：通过 LLM 处理未识别项）
    if unrecognized_options:
        # handle_unrecognized_options(github_actions_job, unrecognized_options)
        handle_unrecognized_options_by_merged(github_actions_job, unrecognized_options)
    # 构建完整 workflow
    return github_actions_job


def handle_timeout(job: Dict[str, Any], params: Dict[str, Any]):
    """处理 timeout 配置"""
    time = params.get("time", 0)
    unit = params.get("unit", "MINUTES").upper()

    if unit == "HOURS":
        job["timeout-minutes"] = time * 60
    elif unit == "MINUTES":
        job["timeout-minutes"] = time
    else:
        job.setdefault("notes", []).append(
            f"# ⚠️ Unsupported timeout unit: {unit}, using minutes"
        )
        job["timeout-minutes"] = time


def handle_retry(job: Dict[str, Any], params: int):
    """处理 retry 配置"""
    job["strategy"] = {
        "retry": {
            "max": params
        }
    }


def handle_build_discarder(job: Dict[str, Any], params: Dict[str, Any]):
    """处理构建记录保留策略（最终增强版）"""
    logrotator_params = {}

    # 自动修复键名包含参数的格式（如 'logRotator(numToKeepStr'）
    for key in list(params.keys()):  # 转换为 list 避免遍历时修改字典
        if key.startswith("logRotator"):
            # 处理键名包含括号的格式（如 'logRotator(numToKeepStr'）
            if '(' in key and not key.endswith(')'):
                # 使用正则提取参数名和值
                match = re.match(r'logRotator\((\w+)(?:Str)?', key)
                if match:
                    param_name = match.group(1)
                    param_value = params[key]
                    logrotator_params[param_name] = param_value.strip("'\"")
                    del params[key]  # 删除旧键

    # 合并标准格式参数（如 {'logRotator': ...}）
    if 'logRotator' in params:
        logrotator_params.update(params['logRotator'])

    # 提取保留数量（优先取 numToKeep）
    keep_num = logrotator_params.get('numToKeep') or logrotator_params.get('numToKeepStr')

    if keep_num:
        job.setdefault("notes", []).extend([
            "# buildDiscarder requires repository-level settings:",
            "# Settings → Actions → General → Workflow run retention",
            f"# Recommended to keep the last {keep_num} workflow runs"
        ])


def handle_unrecognized_options(job: Dict[str, Any], options: list):
    """处理未识别的配置项（改进版，支持内容合并）"""
    for option_name, option_params in options:
        output = query_llm_deepseek(construct_prompt((option_name, option_params)))
        cleaned_output = sanitize_llm_output(output)

        try:
            parsed_output = json.loads(cleaned_output)
            if isinstance(parsed_output, dict):
                # 特殊处理 notes 字段
                if 'notes' in parsed_output:
                    existing_notes = job.get('notes', [])
                    new_notes = parsed_output.pop('notes')
                    if isinstance(new_notes, list):
                        existing_notes.extend(new_notes)
                        job['notes'] = existing_notes

                # 合并其他字段（支持嵌套字典合并）
                for key, value in parsed_output.items():
                    if isinstance(value, dict) and isinstance(job.get(key), dict):
                        job[key].update(value)
                    else:
                        job[key] = value
        except (json.JSONDecodeError, AttributeError) as e:
            logger.error(f"Error merging LLM output: {str(e)}")
            job.setdefault('notes', []).append(f"# 自动转换失败: {option_name} (原始值: {option_params})")


def handle_unrecognized_options_by_merged(job: Dict[str, Any], options: list):
    """批量处理未识别的配置项（减少 API 调用次数）"""
    if not options:
        return

    # 构造批量请求提示词
    batch_prompt = construct_batch_prompt(options)

    # 单次 API 调用获取所有转换建议
    batch_output = query_llm_deepseek(batch_prompt)
    logger.info(f"batch_output: {batch_output}")

    cleaned_output = sanitize_llm_output(batch_output)
    logger.info(f"cleaned_output: {cleaned_output}")

    try:
        parsed_output = json.loads(cleaned_output)
        if isinstance(parsed_output, dict):
            merge_llm_output(job, parsed_output)
    except (json.JSONDecodeError, AttributeError) as e:
        logger.error(f"批量转换失败: {str(e)}")
        job.setdefault('notes', []).append("# 部分自动转换失败，请手动检查")


def construct_batch_prompt(options: list) -> str:
    """构造批量处理提示词"""
    options_desc = "\n".join(
        f"- {name}: {params}"
        for name, params in options
    )
    return (
        "Please batch convert the following Jenkins options to GitHub Actions configurations:\n"
        f"{options_desc}\n"
        "Requirements:\n"
        "1. Use strict JSON format for output\n"
        "2. Combine all conversion results into a single JSON object\n"
        "3. Preserve the original parameter structure"
    )


def merge_llm_output(target: Dict[str, Any], source: Dict[str, Any]):
    """智能合并大模型输出（支持嵌套字段）"""
    # 处理 notes 字段
    if 'notes' in source:
        existing_notes = target.get('notes', [])
        new_notes = source.pop('notes')
        if isinstance(new_notes, list):
            existing_notes.extend(new_notes)
            target['notes'] = existing_notes

    # 递归合并字典
    for key, value in source.items():
        if isinstance(value, dict):
            node = target.setdefault(key, {})
            if isinstance(node, dict):
                node.update(value)
            else:
                target[key] = value
        else:
            target[key] = value


def query_llm_deepseek(prompt):
    """
    使用 OpenAI GPT-4 模型生成响应。
    :param prompt: 提示内容
    :return: GPT-4 的响应
    """
    system_prompt = construct_system_prompt()
    logger.info(f"=== System Prompt ===:\n {system_prompt} \n === System Prompt End ===")
    logger.info(f"=== User Prompt ===:\n {prompt} \n === User Prompt End ===")

    try:
        api_key = os.getenv("SK")
        base_url = os.getenv("LLM_URL")
        model = os.getenv("MODEL", "deepseek-v3")
        
        client = OpenAI(api_key=api_key, base_url=base_url)
        # 调用API
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"


def sanitize_llm_output(llm_text: str) -> str:
    """
    清理大模型返回的字符串，去掉可能的Markdown代码块标记等。
    也可在里面做其他简单的正则清洗。
    """
    # 去掉Markdown式的```json ... ```包裹
    # 注意：此处是一个简单示例，可能需要更健壮的正则
    llm_text = re.sub(r'```(?:json)?(.*?)```', r'\1', llm_text, flags=re.DOTALL)
    return llm_text.strip()


def option_to_yaml(jenkinsfile_content: str, scope="global") -> Dict[str, Any]:
    options = parse_options_block(jenkinsfile_content, scope)
    # 检查options是否为None或空
    if options is None or not options:
        logger.info("No options found in Jenkinsfile.groovy")
        return {}  # 返回空字典

    if scope == "stage":
        # 生成 YAML 字典
        try:
            github_actions_yaml_dict = generate_yaml(options)
            return github_actions_yaml_dict
        except Exception as e:
            logger.error(f"Error generating YAML from options: {str(e)}")
            return {}  # 发生错误时返回空字典
    else:
        # 生成 YAML 字典
        try:
            github_actions_yaml_dict = generate_yaml(options)
            jenkins_comparison = JenkinsComparisonSingle()
            jenkins_comparison.add_comparison(yaml_to_string(github_actions_yaml_dict),'options', scope)
            return github_actions_yaml_dict
        except Exception as e:
            logger.error(f"Error generating YAML from options: {str(e)}")
            return {}  # 发生错误时返回空字典


# def main():
#     # 读取 Jenkinsfile.groovy.groovy内容
#     try:
#         with open('../Jenkinsfile.groovy', 'r') as f:
#             jenkinsfile_content = f.read()
#     except FileNotFoundError:
#         logger.error("Jenkinsfile.groovy.groovy not found in the current directory.")
#         return
#     # 解析环境变量
#     options = parse_options_block(jenkinsfile_content)
#
#     print("options: ")
#     print(options)
#
#     if not options:
#         print("No options variables found in Jenkinsfile.groovy.")
#         return
#
#     # 生成 YAML 字典
#     github_actions_yaml_dict = generate_yaml(options)
#
#     print("github_actions_yaml_dict: ")
#     print(github_actions_yaml_dict)
#
#     # 使用 ruamel.yaml 生成 YAML 字符串
#     yaml = YAML()
#     yaml.default_flow_style = False
#     yaml.indent(mapping=2, sequence=4, offset=2)
#
#     # 写入文件
#     output_file = 'github_actions_options.yaml'
#     with open(output_file, 'w') as f:
#         yaml.dump(github_actions_yaml_dict, f)
#
#     # 输出结果
#     print("Generated GitHub Actions Options YAML:")
#     with open(output_file, 'r') as f:
#         print(f.read())
#     print(f"Saved to {output_file}")
#
#
# if __name__ == "__main__":
#     main()

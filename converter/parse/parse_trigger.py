import re
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import PlainScalarString
from typing import Dict, Any, List

from converter.utils.JenkinsComparisonSingle import JenkinsComparisonSingle
from converter.utils.extract_block_by_scope import extract_block_by_scope
from converter.utils.extract_complete_block import extract_complete_block_with_normalized_indentation
from converter.utils.getLogger import setup_logging
from converter.utils.yaml_to_string import yaml_to_string

# 设置日志
logger = setup_logging()


def parse_triggers_block(jenkinsfile_content: str) -> Dict[str, Any]:
    """
    解析 Jenkinsfile.groovy 中的 triggers 块，收集常见的触发器配置。
    返回一个 dict，用于后续转换到 GitHub Actions 的 on: 结构。
    """
    triggers_config = {
        "cron_list": [],      # 存储所有 cron(...) 表达式
        "github_push": False, # 是否存在 githubPush()
        "poll_scm": [],       # pollSCM(...) 的表达式（通常是 cron 字符串）
        "upstream": []        # upstream(...) 里的信息
        # 也可根据需要添加更多
    }

    # 1. 匹配 triggers { ... } 块
    triggers_pattern = re.compile(r'triggers\s*\{(.*?)}', re.DOTALL)
    triggers_match = triggers_pattern.search(jenkinsfile_content)
    if not triggers_match:
        logger.info("No triggers block found in Jenkinsfile.groovy.")
        return triggers_config  # 没有 triggers 块则返回空的

    triggers_body = triggers_match.group(1)

    # 2. 分别匹配常见语句

    # 2.1 匹配 cron('...') => 提取内部表达式
    cron_pattern = re.compile(r'cron\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)')
    cron_matches = cron_pattern.findall(triggers_body)
    for cm in cron_matches:
        triggers_config["cron_list"].append(cm.strip())

    # 2.2 匹配 githubPush()
    # 简单检测函数名即可
    githubpush_pattern = re.compile(r'githubPush\s*\(\s*\)')
    if githubpush_pattern.search(triggers_body):
        triggers_config["github_push"] = True

    # 2.3 匹配 pollSCM('...') => 提取内部轮询频率
    pollscm_pattern = re.compile(r'pollSCM\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)')
    pollscm_matches = pollscm_pattern.findall(triggers_body)
    for pm in pollscm_matches:
        triggers_config["poll_scm"].append(pm.strip())

    # 2.4 匹配 upstream(...) => 这里简单做一下示例解析
    #   upstream(upstreamProjects: 'other-job', threshold: hudson.model.Result.SUCCESS)
    #   可以再细分捕获 upstreamProjects 的值，但此处仅做示范
    upstream_pattern = re.compile(r'upstream\s*\((.*?)\)')
    upstream_matches = upstream_pattern.findall(triggers_body)
    for um in upstream_matches:
        triggers_config["upstream"].append(um.strip())

    logger.info(f"Triggers Parsed:: {triggers_config}")
    return triggers_config


def generate_yaml_for_triggers(triggers: Dict[str, Any]) -> Dict[str, Any]:
    """
    将从 Jenkins triggers 块解析出的信息转换成 GitHub Actions 格式的 on: 触发器。
    返回一个可被 ruamel.yaml 序列化的字典结构。
    """
    # GitHub Actions 的 on: 字段
    # 里面可以包含 push, pull_request, schedule, workflow_run, etc.
    on_block = {}

    # 1) 如果有 cron_list，就生成 schedule:
    #    - cron: '表达式'
    # Jenkins 中常见的 'H/15 * * * *' 等，需要注意 "H" 并不是 GH Actions 原生支持的写法。
    # 这里示范性地原样放入；若要真正落地，可以考虑把 'H' 替换成具体分钟。
    if triggers["cron_list"]:
        on_block["schedule"] = []
        for cron_expr in triggers["cron_list"]:
            on_block["schedule"].append({"cron": cron_expr})

    # 2) 如果存在 githubPush，则添加 push: {}
    if triggers["github_push"]:
        # 在 GH Actions 中常见做法是：
        # on:
        #   push:
        #     branches: [ 'main', 'dev' ]
        # 这里仅示范写一个空 push: {}，可根据需要拓展
        on_block["push"] = {}

    # 3) 对 pollSCM(...) 暂无原生对应，一般通过 push/pull_request 或 schedule 替代
    #    如果需要保留提示信息，可将 pollSCM 的表达式放入注释或日志中
    if triggers["poll_scm"]:
        # 这里只是演示：把 pollSCM 频率（cron）也放到 schedule 做参考
        # 实际上 GH Actions 没有 pollSCM，通常不用轮询。
        if "schedule" not in on_block:
            on_block["schedule"] = []
        for poll_expr in triggers["poll_scm"]:
            on_block["schedule"].append({"cron": f"# pollSCM -> {poll_expr}"})

    # 4) 对 upstream(...) 在 GH Actions 中可通过 workflow_run 或 repository_dispatch 实现
    #    这里只给示例写一个注释性输出
    if triggers["upstream"]:
        on_block["workflow_run"] = {
            "workflows": ["# Detected Jenkins upstream(...) config"],
            "types": ["completed"]
        }

    # 最终 YAML 结构，如:
    # {
    #   on: {
    #     schedule: [ { cron: '...' } ],
    #     push: {},
    #     workflow_run: { ... }
    #   }
    # }
    yaml_dict = {
        PlainScalarString("on"): on_block
    }
    return yaml_dict


def main():
    # 读取 Jenkinsfile.groovy 内容
    try:
        with open('../Jenkinsfile.groovy', 'r') as f:
            jenkinsfile_content = f.read()
    except FileNotFoundError:
        logger.error("Jenkinsfile.groovy not found in the current directory.")
        return

    # 解析 triggers
    triggers_result = parse_triggers_block(jenkinsfile_content)

    if not triggers_result or all(not v for v in triggers_result.values()):
        print("No triggers found or triggers block is empty in Jenkinsfile.groovy.")
        return

    # 将解析结果转换为 GitHub Actions YAML 片段
    github_actions_yaml_dict = generate_yaml_for_triggers(triggers_result)

    # 使用 ruamel.yaml 生成 YAML 字符串
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)

    # 写入文件
    output_file = 'github_actions_triggers.yaml'
    with open(output_file, 'w') as f:
        yaml.dump(github_actions_yaml_dict, f)

    # 输出结果
    print("Generated GitHub Actions Triggers YAML:")
    with open(output_file, 'r') as f:
        print(f.read())
    print(f"Saved to {output_file}")


if __name__ == "__main__":
    main()


def trigger_to_yaml(jenkinsfile_content: str) -> Dict[str, Any]:
    # 解析 triggers
    triggers_result = parse_triggers_block(jenkinsfile_content)
    if not triggers_result or all(not v for v in triggers_result.values()):
        logger.info("No triggers found or triggers block is empty in Jenkinsfile.groovy.")
        return {}

    # 将解析结果转换为 GitHub Actions YAML 片段
    github_actions_yaml_dict = generate_yaml_for_triggers(triggers_result)
    jenkins_comparison = JenkinsComparisonSingle()
    jenkins_comparison.add_comparison(yaml_to_string(github_actions_yaml_dict), 'environment')
    return github_actions_yaml_dict

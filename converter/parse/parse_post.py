import re
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import PlainScalarString
from typing import Dict, Any, List

from converter.convert.convert_stage import GitHubActionsConverter
from converter.parse.parse_steps import parse_jenkins_steps
from converter.plugins.load_plugins import load_plugins
from converter.utils.JenkinsComparisonSingle import JenkinsComparisonSingle
from converter.utils.extract_complete_block import extract_complete_block_with_normalized_indentation
from converter.utils.find_matching_brace import find_matching_brace
from converter.utils.getLogger import setup_logging
from converter.utils.extract_block_by_scope import extract_block_by_scope
from converter.utils.yaml_to_string import yaml_to_string

# 设置日志
logger = setup_logging()


# Jenkins Post 条件到 GitHub Actions 条件的映射
POST_CONDITION_MAPPING = {
    'always': 'always()',
    'success': 'success()',
    'failure': 'failure()',
    'unstable': None,  # 需要自定义逻辑
    'changed': None,  # 需要自定义逻辑
    'aborted': 'cancelled()',
    'fixed': None,  # 需要自定义逻辑
    'regression': None,  # 需要自定义逻辑
    'cleanup': 'always()'  # cleanup 在 GitHub Actions 中使用 always() 并放在最后
}

# # 常见 Jenkins 步骤映射到 GitHub Actions 步骤
# STEPS_MAPPING = {
#     'echo': {'action': 'run', 'simple': True},
#     'sh': {'action': 'run', 'simple': True},
#     'cleanWs': {'action': 'run', 'command': 'echo "清理工作区 - GitHub Actions 在工作流结束后自动清理"',
#                 'simple': False},
#     'deleteDir': {'action': 'run', 'command': 'echo "删除目录 - GitHub Actions 在工作流结束后自动清理"',
#                   'simple': False},
#     'archiveArtifacts': {'action': 'uses', 'uses': 'actions/upload-artifact@v4', 'simple': False},
#     'junit': {'action': 'uses', 'uses': 'EnricoMi/publish-unit-test-result-action@v2', 'simple': False},
#     'slackSend': {'action': 'uses', 'uses': 'rtCamp/action-slack-notify@v2', 'simple': False},
#     'emailext': {'action': 'uses', 'uses': 'dawidd6/action-send-mail@v3', 'simple': False}
# }


# def parse_post_block(jenkinsfile_content: str, scope="global") -> Dict[str, List[Dict[str, Any]]]:
#     """
#     解析 Jenkinsfile.groovy 中的 post 块，提取条件和步骤信息。
#     """
#     post_blocks = {}
#     # 提取 post 块
#     post_content = extract_block(jenkinsfile_content, 'post')
#     logger.info(f"Post_content: {post_content}")
#     if not post_content:
#         logger.info("No post block found in Jenkinsfile.groovy. ")
#         return post_blocks  # 没有 post 定义
#
#     # 提取每个条件块
#     for condition in list(POST_CONDITION_MAPPING.keys()) + ['unstable', 'changed', 'fixed', 'regression', 'cleanup']:
#         # 使用正则表达式查找条件块
#         condition_pattern = re.compile(r'\b' + re.escape(condition) + r'\s*\{', re.DOTALL)
#         match = condition_pattern.search(post_content)
#
#         if match:
#             start_brace_pos = match.end() - 1
#             end_brace_pos = find_matching_brace(post_content, start_brace_pos)
#
#             if end_brace_pos != -1:
#                 condition_content = post_content[start_brace_pos + 1:end_brace_pos].strip()
#                 logger.info(f"Found condition block: {condition}")
#
#                 # 解析条件块中的步骤
#                 steps = parse_steps(condition_content)
#                 post_blocks[condition] = steps
#
#     logger.info(f"Post blocks parsed: {list(post_blocks.keys())}")
#     return post_blocks
def parse_post_block(content: str, scope="global") -> Dict[str, List[Dict[str, Any]]]:
    """
    解析 Jenkinsfile.groovy 中的 post 块，提取条件和步骤信息。

    参数:
        content: 要解析的内容，可以是整个Jenkinsfile内容或单个stage块内容
        scope: 解析范围 - "global"表示Pipeline级别, "stage"表示Stage级别
    """
    post_blocks = {}

    # 使用通用函数提取post块内容
    post_content = extract_block_by_scope(content, 'post', scope)

    if not post_content:
        logger.info(f"No post block found at {scope} level.")
        return post_blocks

    logger.info(f"Post_content [{scope}]: {post_content}")

    # 提取每个条件块 - 这部分保持不变
    for condition in list(POST_CONDITION_MAPPING.keys()) + ['unstable', 'changed', 'fixed', 'regression', 'cleanup']:
        # 使用正则表达式查找条件块
        condition_pattern = re.compile(r'\b' + re.escape(condition) + r'\s*\{', re.DOTALL)
        match = condition_pattern.search(post_content)

        if match:
            start_brace_pos = match.end() - 1
            end_brace_pos = find_matching_brace(post_content, start_brace_pos)

            if end_brace_pos != -1:
                condition_content = post_content[start_brace_pos + 1:end_brace_pos].strip()
                logger.info(f"Found condition block [{scope}]: {condition}")

                # 解析条件块中的步骤
                steps = parse_jenkins_steps(condition_content)
                logger.info(f"Condition_content: {condition_content}")
                post_blocks[condition] = steps

    logger.info(f"Post blocks parsed [{scope}]: {list(post_blocks.keys())}")
    return post_blocks


# def parse_steps(steps_content: str) -> List[Dict[str, Any]]:
#     """
#     解析 post 条件块中的步骤。
#     """
#     steps = []
#
#     # 简单的 echo 步骤 - 匹配带引号的
#     echo_pattern = re.compile(r'echo\s+[\'"]([^\'"]*)[\'"]')
#     for m in echo_pattern.finditer(steps_content):
#         message = m.group(1)
#         steps.append({
#             'type': 'echo',
#             'message': message
#         })
#
#     # 简单的 sh 步骤
#     sh_pattern = re.compile(r'sh\s+[\'"]([^\'"]*)[\'"]')
#     for m in sh_pattern.finditer(steps_content):
#         command = m.group(1)
#         steps.append({
#             'type': 'sh',
#             'command': command
#         })
#
#     # 清理工作区 cleanWs
#     if 'cleanWs' in steps_content:
#         steps.append({
#             'type': 'cleanWs'
#         })
#
#     # 删除目录 deleteDir
#     if 'deleteDir' in steps_content:
#         steps.append({
#             'type': 'deleteDir'
#         })
#
#     # 归档构件 archiveArtifacts
#     archive_pattern = re.compile(
#         r'archiveArtifacts\s+(?:artifacts:\s*)?[\'"]([^\'"]*)[\'"](?:,\s*allowEmptyArchive:\s*(true|false))?')
#     for m in archive_pattern.finditer(steps_content):
#         artifacts, allow_empty = m.groups()
#         steps.append({
#             'type': 'archiveArtifacts',
#             'artifacts': artifacts,
#             'allowEmptyArchive': allow_empty == 'true' if allow_empty else None
#         })
#
#     # 对于具有键值对参数的 archiveArtifacts
#     alt_archive_pattern = re.compile(r'archiveArtifacts\s+artifacts:\s*[\'"]([^\'"]*)[\'"]')
#     for m in alt_archive_pattern.finditer(steps_content):
#         if not any(step.get('type') == 'archiveArtifacts' for step in steps):  # 避免重复
#             artifacts = m.group(1)
#             steps.append({
#                 'type': 'archiveArtifacts',
#                 'artifacts': artifacts
#             })
#
#     # 测试结果 junit
#     junit_pattern = re.compile(r'junit\s+[\'"]([^\'"]*)[\'"]')
#     for m in junit_pattern.finditer(steps_content):
#         test_results = m.group(1)
#         steps.append({
#             'type': 'junit',
#             'testResults': test_results
#         })
#
#     # Slack 通知 slackSend - 处理各种参数组合
#     slack_pattern = re.compile(
#         r'slackSend\s+(?:channel:\s*[\'"]([^\'"]*)[\'"])?,?\s*(?:color:\s*[\'"]([^\'"]*)[\'"])?,?\s*(?:message:\s*[\'"]([^\'"]*)[\'"])?')
#     for m in slack_pattern.finditer(steps_content):
#         channel, color, message = m.groups()
#         steps.append({
#             'type': 'slackSend',
#             'channel': channel,
#             'color': color,
#             'message': message
#         })
#
#     # 邮件通知 emailext - 处理参数化格式
#     email_pattern = re.compile(
#         r'emailext\s*\(\s*subject:\s*[\'"]([^\'"]*)[\'"],\s*body:\s*[\'"]([^\'"]*)[\'"],\s*to:\s*[\'"]([^\'"]*)[\'"]')
#     for m in email_pattern.finditer(steps_content):
#         subject, body, to = m.groups()
#         steps.append({
#             'type': 'emailext',
#             'subject': subject,
#             'body': body,
#             'to': to
#         })
#
#     return steps


# def convert_to_github_actions(post_blocks: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
#     """
#     将 Jenkins post 块转换为 GitHub Actions 步骤。
#     """
#     github_steps = []
#
#     # 处理每个条件
#     for condition, steps in post_blocks.items():
#         condition_name = condition
#         github_condition = POST_CONDITION_MAPPING.get(condition)
#         # 加载插件
#         logger.info("准备加载plugin！")
#         plugins = load_plugins('plugins')
#         logger.info("成功加载plugin！")
#         if not plugins:
#             logger.warning("No plugins loaded. All steps will use the llm converter.")
#
#         # 初始化转换器
#         converter = GitHubActionsConverter(plugins)
#
#         # 处理特殊条件
#         if condition == 'unstable':
#             # 添加自定义逻辑来检测不稳定状态
#             github_steps.append({
#                 'name': 'Check for unstable build',
#                 'id': 'check_unstable',
#                 'run': (
#                     '# 这里可以添加检测不稳定状态的逻辑，例如某些测试失败但构建成功\n'
#                     'if [ "$SOME_CONDITION" = "true" ]; then\n'
#                     '  echo "is_unstable=true" >> $GITHUB_OUTPUT\n'
#                     'else\n'
#                     '  echo "is_unstable=false" >> $GITHUB_OUTPUT\n'
#                     'fi'
#                 )
#             })
#             github_condition = 'steps.check_unstable.outputs.is_unstable == \'true\''
#
#         elif condition == 'changed':
#             # 添加自定义逻辑来检测状态变化
#             github_steps.append({
#                 'name': 'Check if build status changed',
#                 'id': 'check_changed',
#                 'run': (
#                     '# 这里需要一些额外逻辑来比较当前构建状态与前一个构建\n'
#                     '# 例如，可以使用 GitHub API 或缓存状态\n'
#                     'echo "status_changed=true" >> $GITHUB_OUTPUT'
#                 )
#             })
#             github_condition = 'steps.check_changed.outputs.status_changed == \'true\''
#
#         elif condition == 'fixed':
#             # 添加自定义逻辑来检测修复状态
#             github_steps.append({
#                 'name': 'Check if build was fixed',
#                 'id': 'check_fixed',
#                 'run': (
#                     '# 需要逻辑来确定当前构建是否修复了前一个失败的构建\n'
#                     'echo "is_fixed=true" >> $GITHUB_OUTPUT'
#                 )
#             })
#             github_condition = 'success() && steps.check_fixed.outputs.is_fixed == \'true\''
#
#         elif condition == 'regression':
#             # 添加自定义逻辑来检测回归状态
#             github_steps.append({
#                 'name': 'Check for regression',
#                 'id': 'check_regression',
#                 'run': (
#                     '# 需要逻辑来确定当前构建是否从之前的成功状态回归\n'
#                     'echo "has_regressed=true" >> $GITHUB_OUTPUT'
#                 )
#             })
#             github_condition = 'failure() && steps.check_regression.outputs.has_regressed == \'true\''
#
#         else:
#             # 为每个步骤创建 GitHub Actions 步骤
#             convert_steps = converter.convert_steps(steps)
#
#             # 创建job基础配置，按照期望的顺序添加键
#             job_config = {f"post-{condition_name}": {'runs-on': 'ubuntu-latest', 'if': github_condition,
#                                                      'name': f"On-{condition_name}-post", 'steps': convert_steps}}
#             github_steps.append(job_config)
#         # for step in steps:
#         #     step_type = step['type']
#         #     step_name = f"On {condition_name}: {step_type}"
#         #
#         #     # 根据步骤类型构建 GitHub Actions 步骤
#         #     if step_type == 'echo':
#         #         github_step = {
#         #             'name': step_name,
#         #             'if': github_condition,
#         #             'run': step_type + " '" + step['message'] + "'"
#         #         }
#         #
#         #     elif step_type == 'sh':
#         #         github_step = {
#         #             'name': step_name,
#         #             'if': github_condition,
#         #             'run': step['command']
#         #         }
#         #
#         #     elif step_type == 'cleanWs' or step_type == 'deleteDir':
#         #         github_step = {
#         #             'name': step_name,
#         #             'if': github_condition,
#         #             'run': STEPS_MAPPING[step_type]['command']
#         #         }
#         #
#         #     elif step_type == 'archiveArtifacts':
#         #         github_step = {
#         #             'name': step_name,
#         #             'if': github_condition,
#         #             'uses': STEPS_MAPPING[step_type]['uses'],
#         #             'with': {
#         #                 'name': 'build-artifacts',
#         #                 'path': step['artifacts'],
#         #                 'if-no-files-found': 'warn' if step.get('allowEmptyArchive') else 'error'
#         #             }
#         #         }
#         #
#         #     elif step_type == 'junit':
#         #         github_step = {
#         #             'name': step_name,
#         #             'if': github_condition,
#         #             'uses': STEPS_MAPPING[step_type]['uses'],
#         #             'with': {
#         #                 'files': step['testResults']
#         #             }
#         #         }
#         #
#         #     elif step_type == 'slackSend':
#         #         github_step = {
#         #             'name': step_name,
#         #             'if': github_condition,
#         #             'uses': STEPS_MAPPING[step_type]['uses'],
#         #             'env': {
#         #                 'SLACK_CHANNEL': step.get('channel', 'builds'),
#         #                 'SLACK_COLOR': step.get('color', 'good'),
#         #                 'SLACK_MESSAGE': step.get('message',
#         #                                           f'Build {condition_name}: ${{{{ github.workflow }}}} ${{{{ github.run_number }}}}'),
#         #                 'SLACK_WEBHOOK': '${{ secrets.SLACK_WEBHOOK }}'
#         #             }
#         #         }
#         #
#         #     elif step_type == 'emailext':
#         #         github_step = {
#         #             'name': step_name,
#         #             'if': github_condition,
#         #             'uses': STEPS_MAPPING[step_type]['uses'],
#         #             'with': {
#         #                 'server_address': 'smtp.gmail.com',  # 这里使用默认值，实际应用中应该配置
#         #                 'server_port': 465,
#         #                 'username': '${{ secrets.EMAIL_USERNAME }}',
#         #                 'password': '${{ secrets.EMAIL_PASSWORD }}',
#         #                 'subject': step.get('subject',
#         #                                     f'Build {condition_name}: ${{{{ github.workflow }}}} ${{{{ github.run_number }}}}'),
#         #                 'body': step.get('body',
#         #                                  f'Build info: https://github.com/${{{{ github.repository }}}}/actions/runs/${{{{ github.run_id }}}}'),
#         #                 'to': step.get('to', 'team@example.com'),
#         #                 'from': 'CI System'
#         #             }
#         #         }
#         #
#         #     else:
#         #         logger.warning(f"Unsupported step type: {step_type}")
#         #         continue
#
#     return github_steps

def convert_to_github_actions(post_blocks: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    将 Jenkins post 块转换为 GitHub Actions 步骤。
    """
    github_steps = []

    # 处理每个条件
    for condition, steps in post_blocks.items():
        condition_name = condition
        github_condition = POST_CONDITION_MAPPING.get(condition)

        # 加载插件
        logger.info("准备加载plugin！")
        plugins = load_plugins('plugins')
        logger.info("成功加载plugin！")
        if not plugins:
            logger.warning("No plugins loaded. All steps will use the llm converter.")

        # 初始化转换器
        converter = GitHubActionsConverter(plugins)

        # 处理特殊条件 - 创建相应的job
        if condition == 'unstable':
            # 创建不稳定状态检查步骤
            unstable_check_step = {
                'name': 'Check for unstable build',
                'id': 'check_unstable',
                'run': (
                    '# 这里可以添加检测不稳定状态的逻辑，例如某些测试失败但构建成功\n'
                    'if [ "$SOME_CONDITION" = "true" ]; then\n'
                    '  echo "Build is unstable"\n'
                    'else\n'
                    '  echo "Build is not unstable"\n'
                    'fi'
                )
            }
            # 创建正常的任务步骤
            converted_steps = converter.convert_steps(steps)
            # 将检查步骤添加到步骤列表的开头
            all_steps = [unstable_check_step] + converted_steps

            # 创建job配置
            job_config = {
                f"post-{condition_name}": {
                    'runs-on': 'ubuntu-latest',
                    'if': 'success() && !failure()',  # 近似模拟不稳定状态
                    'name': f"On-{condition_name}-post",
                    'steps': all_steps
                }
            }
            github_steps.append(job_config)

        elif condition == 'changed':
            # 创建状态变化检查步骤
            change_check_step = {
                'name': 'Check if build status changed',
                'id': 'check_changed',
                'run': (
                    '# 这里需要一些额外逻辑来比较当前构建状态与前一个构建\n'
                    '# 例如，可以使用 GitHub API 或缓存状态\n'
                    'echo "Checking if build status changed"'
                )
            }
            # 创建正常的任务步骤
            converted_steps = converter.convert_steps(steps)
            # 将检查步骤添加到步骤列表的开头
            all_steps = [change_check_step] + converted_steps

            # 创建job配置
            job_config = {
                f"post-{condition_name}": {
                    'runs-on': 'ubuntu-latest',
                    'name': f"On-{condition_name}-post",
                    'if': 'always()',  # 始终运行，但内部步骤会检查状态变化
                    'steps': all_steps
                }
            }
            github_steps.append(job_config)

        elif condition == 'fixed':
            # 创建修复检查步骤
            fixed_check_step = {
                'name': 'Check if build was fixed',
                'id': 'check_fixed',
                'run': (
                    '# 需要逻辑来确定当前构建是否修复了前一个失败的构建\n'
                    'echo "Checking if build was fixed"'
                )
            }
            # 创建正常的任务步骤
            converted_steps = converter.convert_steps(steps)
            # 将检查步骤添加到步骤列表的开头
            all_steps = [fixed_check_step] + converted_steps

            # 创建job配置
            job_config = {
                f"post-{condition_name}": {
                    'runs-on': 'ubuntu-latest',
                    'name': f"On-{condition_name}-post",
                    'if': 'success()',  # 当前构建成功
                    'steps': all_steps
                }
            }
            github_steps.append(job_config)

        elif condition == 'regression':
            # 创建回归检查步骤
            regression_check_step = {
                'name': 'Check for regression',
                'id': 'check_regression',
                'run': (
                    '# 需要逻辑来确定当前构建是否从之前的成功状态回归\n'
                    'echo "Checking for regression"'
                )
            }
            # 创建正常的任务步骤
            converted_steps = converter.convert_steps(steps)
            # 将检查步骤添加到步骤列表的开头
            all_steps = [regression_check_step] + converted_steps

            # 创建job配置
            job_config = {
                f"post-{condition_name}": {
                    'runs-on': 'ubuntu-latest',
                    'name': f"On-{condition_name}-post",
                    'if': 'failure()',  # 当前构建失败
                    'steps': all_steps
                }
            }
            github_steps.append(job_config)

        else:
            # 为每个步骤创建 GitHub Actions 步骤
            convert_steps = converter.convert_steps(steps)

            # 创建job基础配置，按照期望的顺序添加键
            job_config = {
                f"post-{condition_name}": {
                    'runs-on': 'ubuntu-latest',
                    'if': github_condition,
                    'name': f"On-{condition_name}-post",
                    'steps': convert_steps
                }
            }
            logger.info(f"Post_Step: {job_config}")
            github_steps.append(job_config)

    logger.info(f"github_steps: {github_steps}")
    return github_steps


def generate_yaml(github_steps: List[Dict[str, Any]], dependencies) -> Dict[str, Any]:
    """
    生成 GitHub Actions 工作流 YAML。
    :param github_steps:
    :param dependencies:
    """
    logger.info(f"generate_yaml: github_steps:{github_steps}")
    # 将github_steps列表中的多个字典合并为一个字典
    jobs_dict = {}
    for step_dict in github_steps:
        jobs_dict.update(step_dict)

    # 从dependencies中提取所有的stage名称
    all_stages = list(dependencies.keys())
    # 处理stage名称：将空格替换为下划线并转为小写
    formatted_stages = [re.sub(r'\s+', '_', stage).lower() for stage in all_stages]
    # 为每个job添加needs字段，包含所有的stage
    for job_name in jobs_dict:
        jobs_dict[job_name]['needs'] = formatted_stages

    yaml_content = {
        # 'name': 'CI/CD Pipeline',
        # PlainScalarString('on'): {
        #     'push': {
        #         'branches': ['main']
        #     },
        #     'pull_request': {
        #         'branches': ['main']
        #     }
        # },
        'jobs': jobs_dict
        # 'jobs': {
        #     'build': {
        #         'runs-on': 'ubuntu-latest',
        #         'steps': [
        #                      {
        #                          'uses': 'actions/checkout@v4'
        #                      },
        #                      {
        #                          'name': 'Build',
        #                          'run': 'echo "Building..."'
        #                      },
        #                      {
        #                          'name': 'Test',
        #                          'run': 'echo "Testing..."'
        #                      },
        #                      {
        #                          'name': 'Deploy',
        #                          'run': 'echo "Deploying..."'
        #                      }
        #                  ] + github_steps
        #     }
        # }
    }
    # logger.info(f"666666666:{yaml_content}")
    return yaml_content


def convert_post_blocks_to_steps(github_steps):
    """
    将job结构的post块转换为stage内的steps结构

    参数:
    github_steps: 包含post块的job结构列表，例如：
        [{'post-success': {'runs-on': 'ubuntu-latest', 'if': 'success()', 'name': 'On-success-post', 'steps': [...]}}, ...]

    返回:
    steps: 转换后的steps列表，用于stage中的steps部分
    """
    stage_steps = []

    for step_dict in github_steps:
        for condition, config in step_dict.items():
            # 从post-success和post-failure...提取success和failure...
            condition_name = condition.replace('post-', '')

            # 获取条件表达式
            if_condition = config.get('if')

            # 获取嵌套步骤
            nested_steps = config.get('steps', [])

            for original_step in nested_steps:
                # 创建有序字典，确保属性按所需顺序排列
                new_step = {}

                # 首先设置步骤名称
                if 'name' in original_step:
                    new_step['name'] = f"Post ({condition_name}): {original_step['name']}"
                else:
                    new_step['name'] = f"Post ({condition_name}): Action step"

                # 其次设置if条件
                new_step['if'] = if_condition

                # 最后复制原始步骤的其他所有属性
                for key, value in original_step.items():
                    if key != 'name':  # 名称已经处理过了
                        new_step[key] = value

                # 添加到结果列表
                stage_steps.append(new_step)
    logger.info(f"stage_steps: {stage_steps}")
    return stage_steps


def post_to_yaml(jenkinsfile_content: str, dependencies, scope="global"):
    # 解析 post 块
    post_blocks = parse_post_block(jenkinsfile_content, scope)

    if not post_blocks:
        logger.info("No post blocks found in Jenkinsfile.groovy.")
        return post_blocks

    # 转换为 GitHub Actions 步骤
    github_steps = convert_to_github_actions(post_blocks)

    if scope == "stage":
        # logger.info("在stage in in in")
        # 在stage内，将job结构转换为step结构后返回
        stage_steps = convert_post_blocks_to_steps(github_steps)
        return stage_steps
    else:
        # 在stage外，返回 YAML 字典
        github_actions_yaml_dict = generate_yaml(github_steps, dependencies)
        jenkins_comparison = JenkinsComparisonSingle()
        jenkins_comparison.add_comparison(yaml_to_string(github_actions_yaml_dict), 'post', scope)
        return github_actions_yaml_dict


# def main():
#     # 读取 Jenkinsfile.groovy 内容
#     try:
#         with open('Jenkinsfile', 'r', encoding='utf-8') as f:
#             jenkinsfile_content = f.read()
#     except FileNotFoundError:
#         try:
#             # 检查父目录
#             with open('../Jenkinsfile.groovy', 'r') as f:
#                 jenkinsfile_content = f.read()
#         except FileNotFoundError:
#             logger.error("Jenkinsfile.groovy not found in the current directory or parent directory.")
#             return
#     from converter.utils.strip_jenkins_comments import remove_groovy_comments
#     jenkinsfile_content = remove_groovy_comments(jenkinsfile_content)
#
#     # 解析 post 块
#     post_blocks = parse_post_block(jenkinsfile_content)
#
#     if not post_blocks:
#         print("No post blocks found in Jenkinsfile.groovy.")
#         return
#
#     # 转换为 GitHub Actions 步骤
#     github_steps = convert_to_github_actions(post_blocks)
#
#     # 生成 YAML 字典
#     github_actions_yaml_dict = generate_yaml(github_steps, dependencies)
#
#     # 使用 ruamel.yaml 生成 YAML 字符串
#     yaml = YAML()
#     yaml.default_flow_style = False
#     yaml.indent(mapping=2, sequence=4, offset=2)
#
#     # 写入文件
#     with open('github_actions_workflow.yaml', 'w') as f:
#         yaml.dump(github_actions_yaml_dict, f)
#
#     # 输出结果
#     print("Generated GitHub Actions Workflow YAML:")
#     with open('github_actions_workflow.yaml', 'r') as f:
#         print(f.read())
#     print("Saved to github_actions_workflow.yaml")


# if __name__ == "__main__":
#     main()



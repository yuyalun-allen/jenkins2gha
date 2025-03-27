from converter.utils.extract_block import extract_block
import re
from converter.utils.find_matching_brace import find_matching_brace
from converter.utils.getLogger import setup_logging

logger = setup_logging()


def extract_complete_block(content: str, block_name: str) -> str:
    """提取包含块名称和完整大括号结构的块内容"""
    # 转义块名称中的特殊字符
    escaped_block = re.escape(block_name)
    pattern = re.compile(rf'{escaped_block}\s*\{{')
    match = pattern.search(content)
    if not match:
        return ""

    start_pos = match.start()
    brace_open_pos = match.end() - 1
    brace_count = 1
    index = brace_open_pos + 1

    while index < len(content) and brace_count > 0:
        if content[index] == '{':
            brace_count += 1
        elif content[index] == '}':
            brace_count -= 1
        index += 1

    return content[start_pos:index].strip() if brace_count == 0 else ""


def extract_complete_block_by_scope(content: str, block_name: str, scope="global") -> str:
    """
        根据指定的作用域提取块内容

        参数:
            content: 要解析的内容
            block_name: 要提取的块名称（如'tools', 'post', 'environment'等）
            scope: 解析范围 - "global"表示Pipeline级别, "stage"表示Stage级别

        返回:
            提取的块内容，如果找不到则返回空字符串
        """
    if scope == "stage":
        # 已经在stage块内，直接提取指定块
        block_content = extract_complete_block(content, block_name)
        if not block_content:
            logger.info(f"No {block_name} block found in stage.")
            return ""
        return block_content
    else:  # global scope
        # 提取pipeline块
        pipeline_content = extract_block(content, 'pipeline')
        if not pipeline_content:
            logger.info("No pipeline block found.")
            return ""

        # 提取stages块
        stages_content = extract_block(pipeline_content, 'stages')

        # 找到stages在pipeline中的位置
        if stages_content:
            stages_pattern = re.compile(r'stages\s*\{', re.DOTALL)
            stages_match = stages_pattern.search(pipeline_content)

            if stages_match:
                stages_start = stages_match.start()

                # 找到stages块的结束位置
                stages_open = pipeline_content.find('{', stages_start)
                stages_end = find_matching_brace(pipeline_content, stages_open)

                if stages_end != -1:
                    # 创建一个不包含stages块的pipeline内容
                    pipeline_without_stages = pipeline_content[:stages_start] + pipeline_content[stages_end + 1:]

                    # 在不含stages的内容中提取指定块
                    block_content = extract_complete_block(pipeline_without_stages, block_name)
                    if not block_content:
                        logger.info(f"No global {block_name} block found.")
                        return ""
                    return block_content
                else:
                    logger.info("Could not find end of stages block.")
                    return ""
            else:
                logger.info("Stages content found but position not located.")
                return ""
        else:
            # 没有stages块，直接在pipeline内容中提取指定块
            block_content = extract_complete_block(pipeline_content, block_name)
            if not block_content:
                logger.info(f"No global {block_name} block found.")
                return ""
            return block_content


def extract_complete_block_with_normalized_indentation(content: str, block_name: str, scope="global") -> str:
    """
    提取块内容并规范化缩进

    参数:
        content: 要解析的内容
        block_name: 要提取的块名称
        scope: 解析范围 - "global"表示Pipeline级别, "stage"表示Stage级别

    返回:
        已提取且缩进规范化的块内容
    """
    # 首先使用现有函数提取块
    extracted_block = extract_complete_block_by_scope(content, block_name, scope)

    if not extracted_block:
        return ""

    # 按行分割以处理缩进
    lines = extracted_block.split('\n')

    if len(lines) <= 1:
        return extracted_block

    # 找到最小缩进（排除空行）
    non_empty_lines = [line for line in lines[1:] if line.strip()]
    if not non_empty_lines:
        return extracted_block

    min_indent = min(len(line) - len(line.lstrip()) for line in non_empty_lines)

    # 保持第一行不变（包含块名称）
    normalized_lines = [lines[0]]

    # 从后续行中移除最小缩进
    for line in lines[1:]:
        if line.strip():  # 非空行
            normalized_lines.append(line[min_indent:])
        else:  # 空行
            normalized_lines.append('')

    return '\n'.join(normalized_lines)


content = """
pipeline {
    agent any
    options {
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 10, unit: 'HOURS')
        retry(3)
    }
    triggers {
        cron('H 4/* 0 0 1-5')
    }
    parameters {
        string(name: 'BRANCH', defaultValue: 'main', description: 'Git branch to build')
        booleanParam(name: 'DEPLOY', defaultValue: true, description: 'Deploy after build')
        choice(name: 'Choice', choices: ['dev', 'staging', 'production'], description: 'Deployment environment')
        fileParam(name: 'CONFIG_FILE', description: 'Configuration file')
    }
    environment {
        APP_ENV = "production"
        DEPLOY_SERVER = "deploy.example.com"
        VAR1 = "value1"
        VAR2 = "value2"
    }
    tools {
        jdk 'JDK11'
        maven 'Maven3'
        maven 'maven-3.8.1'
        gradle 'gradle-7.5'
        nodejs 'nodejs-16'
        python 'python-3.9'
        ruby 'ruby-2.7'
        ant 'ant-1.10'
        golang 'go-1.19'
        sonarqubeScanner 'sonar-4.0'
        kubernetesCli 'kubectl-1.25'
        dotnetSdk 'dotnet-sdk-6.0'
        ansible 'ansible-2.14'
        jmeter 'jmeter-5.5'
        sbt 'sbt-1.8.0'
        terraform 'terraform-1.3'
    }
    stages {
        stage('Checkout') {
            tools {
                jdk 'jdk11'
            }
            steps {
                git branch: "${params.BRANCH}", url: 'https://github.com/example/repo.git'
            }
        }
        stage('test-parse-steps') {
            steps {
                // 简单shell命令
                sh 'npm install'

                // 带参数的shell命令
                sh "echo 'Current build number: ${BUILD_NUMBER}'"

                // 多行shell命令
                sh '''
                    echo "Starting multi-line shell command"
                    mkdir -p build/reports
                    cp -r src/config/* build/
                    echo "Finished setup"
                '''

                // 带嵌套内容的script块
                script {
                    if (env.BRANCH_NAME == 'master') {
                        sh "docker build -t ${DOCKER_IMAGE}:${BUILD_NUMBER} ."
                        sh 'make build'
                        echo "Built master branch"
                    } else {
                        sh "docker build -t ${DOCKER_IMAGE}:dev-${BUILD_NUMBER} ."
                        echo "Built development branch"
                    }
                }

                // 条件执行
                when {
                    branch 'master'
                }




                // 带超时的步骤
                timeout(time: 5, unit: 'MINUTES') {
                    sh 'npm run integration-tests'
                }

                // 重试机制
                retry(3) {
                    sh 'flaky_command_that_may_fail'
                }


                // 档案存储
                archiveArtifacts artifacts: 'build/libs/*.jar', fingerprint: true

                // 测试结果
                junit 'build/test-results/**/*.xml'
            }
        }
        stage('Build') {
            steps {
                // Get some code from a GitHub repository
                git 'https://github.com/2206-devops-batch/ChrisB-Project1'
                git 'https://gitee.com/2206-devops-batch/ChrisB-Project1'
                // Set Up A Virtual Environment (.venv)
                sh 'python3 -m venv .venv && . .venv/bin/activate'
                // Install Pip & Requirements
                sh 'python3 install -U pip && pip install -r requirements.txt'
            }
        }
        stage('Test'){
            steps {
                // Run pytest
                sh 'python3 -m pytest app_test.py'
            }
        }

        stage('Checkout Code') {
            post {
        success {
            111111111
        }
        failure {
            22222222222
        }
    }
            steps {

                mail to: 'team@example.com',
                     subject: "Build ${currentBuild.fullDisplayName}",
                     body: "Build completed with status: ${currentBuild.currentResult}"

                git branch: 'main',
                    url: 'https://gitee.com/1234567899/your-project.git',
                    credentialsId: 'github-credentials'
                git branch: 'main', url: 'https://github.com/your-repo6666666/your-project.git',credentialsId: 'github-credentials'


                echo "Building with VAR1=${env.VAR1} and VAR2=${env.VAR2}"
            }
        }
    }
    post {
        success {
            slackSend channel: '#deployments', message: "Build and Deployment succeeded for ${env.BRANCH}"
        }
        failure {
            slackSend channel: '#deployments', message: "Build or Deployment failed for ${env.BRANCH}"
        }
    }
}

"""

# print(extract_complete_block_with_normalized_indentation(content, "stage('Build')", "stage"))

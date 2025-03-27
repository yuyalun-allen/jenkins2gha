import re
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import PlainScalarString
from typing import Dict, Any, List, Callable

from converter.utils.JenkinsComparisonSingle import JenkinsComparisonSingle
from converter.utils.extract_complete_block import extract_complete_block_with_normalized_indentation
from converter.utils.getLogger import setup_logging
from converter.utils.extract_block_by_scope import extract_block_by_scope
from converter.utils.yaml_to_string import yaml_to_string

# 设置日志
logger = setup_logging()


# def parse_tools_block(jenkinsfile_content: str) -> List[Dict[str, str]]:
#     """
#     解析 Jenkinsfile.groovy 中的 tools { ... } 块。
#     返回一个列表，每个元素形如:
#         {
#           "tool_type": "maven",
#           "tool_name": "maven-3.8.1"
#         }
#     """
#     tools_list = []
#
#     # 先找出 tools { ... } 主体
#     tools_block_pattern = re.compile(r'tools\s*\{(.*?)}', re.DOTALL)
#     match = tools_block_pattern.search(jenkinsfile_content)
#     if not match:
#         logger.info("No tools block found in Jenkinsfile.groovy.")
#         return tools_list  # 没有 tools 定义
#
#     tools_content = match.group(1)
#
#     # 匹配各行，如 maven 'maven-3.8.1' / jdk 'jdk11' / python "python-3.9" 等
#     # 注意可能有人用单引号，也可能用双引号
#     tool_line_pattern = re.compile(r'(\w+)\s+[\'"]([^\'"]+)[\'"]')
#     for m in tool_line_pattern.finditer(tools_content):
#         tool_type, tool_name = m.groups()
#         tools_list.append({
#             "tool_type": tool_type.strip(),
#             "tool_name": tool_name.strip()
#         })
#
#     logger.info(f"Tools Parsed:: {tools_list}")
#     return tools_list

# --------------------
# 以下是针对每种 tool_type 的转换函数或映射规则
# --------------------
def parse_tools_block(content: str, scope="global") -> List[Dict[str, str]]:
    """
    解析 Jenkinsfile.groovy 中的 tools { ... } 块。

    参数:
        content: 要解析的内容，可以是整个Jenkinsfile内容或单个stage块内容
        scope: 解析范围 - "global"表示Pipeline级别, "stage"表示Stage级别

    返回一个列表，每个元素形如:
        {
          "tool_type": "maven",
          "tool_name": "maven-3.8.1"
        }
    """
    tools_list = []

    # 使用通用函数提取tools块内容
    tools_content = extract_block_by_scope(content, 'tools', scope)

    if not tools_content:
        logger.info(f"No tools block found at {scope} level.")
        return tools_list

    logger.info(f"Tools_content [{scope}]: {tools_content}")

    # 解析工具项 - 这部分保持不变
    tool_line_pattern = re.compile(r'(\w+)\s+[\'"]([^\'"]+)[\'"]')
    for m in tool_line_pattern.finditer(tools_content):
        tool_type, tool_name = m.groups()
        tools_list.append({
            "tool_type": tool_type.strip(),
            "tool_name": tool_name.strip()
        })

    logger.info(f"Tools Parsed [{scope}]: {tools_list}")
    return tools_list


def extract_version_from_name(name: str) -> str:
    """
    从类似 'jdk11', 'maven-3.8.1', 'nodejs-16', 'python-3.9' 这样的字符串中提取数字(含点号)部分。
    简化处理：找第一个匹配 '\\d+(\\.\\d+)*'（一个或多个数字，可能带点）。
    找不到就返回空字符串。
    """
    match = re.search(r'\d+(\.\d+)*', name)
    return match.group(0) if match else ""


def steps_for_jdk(tool_name: str) -> List[Dict[str, Any]]:
    """
    对应 Jenkins:  tools { jdk 'jdk11' }
    转成 GH Actions:
      - name: Set up JDK 11
        uses: actions/setup-java@v4
        with:
          java-version: '11'
          distribution: 'temurin'
    """
    version = extract_version_from_name(tool_name)
    if not version:
        version = "11"  # 默认值
    return [
        {
            "name": f"Set up JDK {version}",
            "uses": "actions/setup-java@v4",
            "with": {
                "java-version": version,
                "distribution": "temurin"  # 可换 'zulu', 'corretto' 等
            }
        }
    ]


def steps_for_maven(tool_name: str) -> List[Dict[str, Any]]:
    """
    对应 Jenkins: tools { maven 'maven-3.8.1' }
    转成 GH Actions 示例:
      - uses: actions/setup-java@v4
        with:
          java-version: '11'
      - name: Run Maven
        run: mvn -B verify
    """
    # 这里示例中并未去强制安装对应版本的 Maven，通常 GitHub Runner 自带或使用 setup-java 来设置 Maven。
    version = extract_version_from_name(tool_name) or "3.8.1"
    return [
        {
            "uses": "actions/setup-java@v4",
            "with": {
                "java-version": "11"
            }
        },
        {
            "name": f"Run Maven (version {version})",
            "run": "mvn -B verify"
        }
    ]


def steps_for_gradle(tool_name: str) -> List[Dict[str, Any]]:
    """
    示例: tools { gradle 'gradle-7.5' }
    转成:
      - uses: actions/setup-java@v4
        with:
          java-version: '11'
      - name: Setup Gradle
        uses: gradle/actions/setup-gradle@v3
        with:
          gradle-version: 7.5
    """
    version = extract_version_from_name(tool_name) or "7.5"
    return [
        {
            "uses": "actions/setup-java@v4",
            "with": {
                "java-version": "11"
            }
        },
        {
            "name": "Setup Gradle",
            "uses": "gradle/actions/setup-gradle@v3",
            "with": {
                "gradle-version": version
            }
        }
    ]


def steps_for_nodejs(tool_name: str) -> List[Dict[str, Any]]:
    """
    示例: tools { nodejs 'nodejs-16' }
      - name: Set up Node.js 16
        uses: actions/setup-node@v4
        with:
          node-version: 16
      - run: npm install
    """
    version = extract_version_from_name(tool_name) or "16"
    return [
        {
            "name": f"Set up Node.js {version}",
            "uses": "actions/setup-node@v4",
            "with": {
                "node-version": version
            }
        },
        {
            "run": "npm install"
        }
    ]


def steps_for_python(tool_name: str) -> List[Dict[str, Any]]:
    """
    示例: tools { python 'python-3.9' }
      - name: Set up Python 3.9
        uses: actions/setup-python@v5
        with:
          python-version: '3.9'
      - run: pip install -r requirements.txt
    """
    version = extract_version_from_name(tool_name) or "3.9"
    return [
        {
            "name": f"Set up Python {version}",
            "uses": "actions/setup-python@v5",
            "with": {
                "python-version": version
            }
        },
        {
            "run": "pip install -r requirements.txt"
        }
    ]


def steps_for_ruby(tool_name: str) -> List[Dict[str, Any]]:
    """
    示例: tools { ruby 'ruby-2.7' }
      - name: Set up Ruby 2.7
        uses: ruby/setup-ruby@v1
        with:
          ruby-version: 2.7
      - run: gem install bundler
    """
    version = extract_version_from_name(tool_name) or "2.7"
    return [
        {
            "name": f"Set up Ruby {version}",
            "uses": "ruby/setup-ruby@v1",
            "with": {
                "ruby-version": version
            }
        },
        {
            "run": "gem install bundler"
        }
    ]


def steps_for_ant(tool_name: str) -> List[Dict[str, Any]]:
    """
    示例: tools { ant 'ant-1.10' }
      - uses: actions/setup-java@v4
        with:
          java-version: '11'
      - name: Install Ant
        run: sudo apt-get install ant
    """
    version = extract_version_from_name(tool_name) or "1.10"
    return [
        {
            "uses": "actions/setup-java@v4",
            "with": {
                "java-version": "11"
            }
        },
        {
            "name": f"Install Ant (version {version})",
            "run": "sudo apt-get install -y ant"
        }
    ]


def steps_for_go(tool_name: str) -> List[Dict[str, Any]]:
    """
    示例: tools { golang 'go-1.19' }
      - name: Set up Go 1.19
        uses: actions/setup-go@v5
        with:
          go-version: '1.19'
      - run: go build
    """
    version = extract_version_from_name(tool_name) or "1.19"
    return [
        {
            "name": f"Set up Go {version}",
            "uses": "actions/setup-go@v5",
            "with": {
                "go-version": version
            }
        },
        {
            "run": "go build"
        }
    ]


def steps_for_sonarqube(tool_name: str) -> List[Dict[str, Any]]:
    """
    示例: tools { sonarqubeScanner 'sonar-4.0' }
      - name: SonarQube Scan
        uses: sonarsource/sonarqube-scan-action@v1
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
    """
    version = extract_version_from_name(tool_name) or "4.0"
    return [
        {
            "name": f"SonarQube Scan (scanner {version})",
            "uses": "sonarsource/sonarqube-scan-action@v1",
            "env": {
                "SONAR_TOKEN": "${{ secrets.SONAR_TOKEN }}"
            }
        }
    ]


def steps_for_kubernetes_cli(tool_name: str) -> List[Dict[str, Any]]:
    """
    示例: tools { kubernetesCli 'kubectl-1.25' }
      - name: Install kubectl
        run: |
          curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
          sudo install kubectl /usr/local/bin/kubectl
    """
    version = extract_version_from_name(tool_name) or "1.25"
    # 这里示例和实际版本并未强绑定，而是抓最新 stable 版
    return [
        {
            "name": f"Install kubectl (desired {version})",
            "run": (
                "curl -LO \"https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)"
                "/bin/linux/amd64/kubectl\"\n"
                "sudo install kubectl /usr/local/bin/kubectl"
            )
        }
    ]


def steps_for_dotnet_sdk(tool_name: str) -> List[Dict[str, Any]]:
    """
    示例: tools { dotnetSdk 'dotnet-sdk-6.0' }
      - name: Setup .NET 6.0
        uses: actions/setup-dotnet@v4
        with:
          dotnet-version: 6.0.x
      - run: dotnet build
    """
    version = extract_version_from_name(tool_name) or "6.0"
    # 将 "6.0" 变为 "6.0.x"
    return [
        {
            "name": f"Setup .NET {version}",
            "uses": "actions/setup-dotnet@v4",
            "with": {
                "dotnet-version": f"{version}.x"
            }
        },
        {
            "run": "dotnet build"
        }
    ]


def steps_for_ansible(tool_name: str) -> List[Dict[str, Any]]:
    """
    示例: tools { ansible 'ansible-2.14' }
      - name: Install Ansible
        run: pip install ansible==2.14
    """
    version = extract_version_from_name(tool_name) or "2.14"
    return [
        {
            "name": f"Install Ansible {version}",
            "run": f"pip install ansible=={version}"
        }
    ]


def steps_for_jmeter(tool_name: str) -> List[Dict[str, Any]]:
    """
    示例: tools { jmeter 'jmeter-5.5' }
      - name: Download JMeter
        run: |
          wget https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-5.5.zip
          unzip apache-jmeter-5.5.zip
      - name: Run JMeter Test
        run: ./apache-jmeter-5.5/bin/jmeter -n -t test.jmx
    """
    version = extract_version_from_name(tool_name) or "5.5"
    return [
        {
            "name": f"Download JMeter {version}",
            "run": (
                f"wget https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-{version}.zip\n"
                f"unzip apache-jmeter-{version}.zip"
            )
        },
        {
            "name": "Run JMeter Test",
            "run": f"./apache-jmeter-{version}/bin/jmeter -n -t test.jmx"
        }
    ]


def steps_for_sbt(tool_name: str) -> List[Dict[str, Any]]:
    """
    示例: tools { sbt 'sbt-1.8.0' }
      - uses: actions/setup-java@v4
        with:
          java-version: '11'
      - name: Setup SBT
        run: |
          curl -L https://piccolo.link/sbt-1.8.0.zip -o sbt.zip
          unzip sbt.zip
      - run: sbt compile
    """
    version = extract_version_from_name(tool_name) or "1.8.0"
    return [
        {
            "uses": "actions/setup-java@v4",
            "with": {
                "java-version": "11"
            }
        },
        {
            "name": f"Setup SBT {version}",
            "run": (
                f"curl -L https://piccolo.link/sbt-{version}.zip -o sbt.zip\n"
                "unzip sbt.zip"
            )
        },
        {
            "run": "sbt compile"
        }
    ]


def steps_for_terraform(tool_name: str) -> List[Dict[str, Any]]:
    """
    示例: tools { terraform 'terraform-1.3' }
      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2
        with:
          terraform_version: 1.3.0
      - run: terraform init
    """
    # 简化处理：若拿到 "1.3" 就拼成 "1.3.0"
    version = extract_version_from_name(tool_name) or "1.3"
    if not version.endswith(".0"):
        version = version + ".0"
    return [
        {
            "name": f"Setup Terraform {version}",
            "uses": "hashicorp/setup-terraform@v2",
            "with": {
                "terraform_version": version
            }
        },
        {
            "run": "terraform init"
        }
    ]


# 将所有工具类型与对应的“生成步骤函数”映射起来：
KNOWN_TOOLS_MAPPING: Dict[str, Callable[[str], List[Dict[str, Any]]]] = {
    "jdk": steps_for_jdk,
    "maven": steps_for_maven,
    "gradle": steps_for_gradle,
    "nodejs": steps_for_nodejs,
    "python": steps_for_python,
    "ruby": steps_for_ruby,
    "ant": steps_for_ant,
    "golang": steps_for_go,             # Jenkins 插件里常写 "golang"
    "go": steps_for_go,                 # 有时也写 "go"
    "sonarqubeScanner": steps_for_sonarqube,
    "kubernetesCli": steps_for_kubernetes_cli,
    "dotnetSdk": steps_for_dotnet_sdk,
    "ansible": steps_for_ansible,
    "jmeter": steps_for_jmeter,
    "sbt": steps_for_sbt,
    "terraform": steps_for_terraform
}


def generate_yaml_for_tools_by_steps(tools_list: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    将 parse_tools_block 得到的 tools 列表转换成 GitHub Actions 的 steps 配置段。
    返回结构示例（可在 jobs.<job>.steps 下使用）：
    [
      { "name": "...", "uses": "...", "with": { ... } },
      { "name": "...", "run": "..." },
    ]
    """
    final_steps = []

    for tool_info in tools_list:
        tool_type = tool_info["tool_type"]
        tool_name = tool_info["tool_name"]

        # 根据工具类型调用相应的转换函数
        if tool_type in KNOWN_TOOLS_MAPPING:
            steps = KNOWN_TOOLS_MAPPING[tool_type](tool_name)
            final_steps.extend(steps)
        else:
            # 未知工具，给一个提示
            final_steps.append({
                "name": f"Install {tool_type} ({tool_name})",
                "run": f"echo 'TODO: Handle {tool_type} version: {tool_name}'"
            })

    # 直接返回steps列表
    return final_steps


def generate_yaml_for_tools_by_jobs(tools_list: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    将 parse_tools_block 得到的 tools 列表转换成 GitHub Actions 的完整结构：
    jobs:
      build:
        runs-on: ubuntu-latest
        steps:
          - name: ...
            uses: ...
            ...
    """

    final_steps = []

    for tool_info in tools_list:
        tool_type = tool_info["tool_type"]
        tool_name = tool_info["tool_name"]

        # 根据工具类型调用相应的转换函数
        if tool_type in KNOWN_TOOLS_MAPPING:
            steps = KNOWN_TOOLS_MAPPING[tool_type](tool_name)
            final_steps.extend(steps)
        else:
            # 未知工具，给一个提示
            final_steps.append({
                "name": f"Install {tool_type} ({tool_name})",
                "run": f"echo 'TODO: Handle {tool_type} version: {tool_name}'"
            })

    # 将 final_steps 封装为 GitHub Actions 的一个 job
    return {
        "jobs": {
            "build-tools": {
                "runs-on": "ubuntu-latest",
                "steps": final_steps
            }
        }
    }


def main():
    # 读取 Jenkinsfile.groovy 内容
    try:
        with open('../Jenkinsfile.groovy', 'r') as f:
            jenkinsfile_content = f.read()
    except FileNotFoundError:
        logger.error("Jenkinsfile.groovy not found in the parent directory.")
        return

    # 解析 tools 块
    tools_list = parse_tools_block(jenkinsfile_content)
    if not tools_list:
        print("No tools block found or no valid tool lines in Jenkinsfile.groovy.")
        return

    # 生成对应的 GitHub Actions steps
    github_actions_steps = generate_yaml_for_tools_by_jobs(tools_list)

    # 使用 ruamel.yaml 序列化为 .yaml 文件
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)

    output_file = 'github_actions_tools.yaml'
    with open(output_file, 'w') as f:
        yaml.dump(github_actions_steps, f)

    # 输出到控制台
    print("Generated GitHub Actions Tools YAML:")
    with open(output_file, 'r') as f:
        print(f.read())
    print(f"Saved to {output_file}")


if __name__ == "__main__":
    main()


def tool_to_yaml(jenkinsfile_content: str, scope="global") -> Dict[str, Any]:

    # 解析 tools 块
    tools_list = parse_tools_block(jenkinsfile_content, scope)
    if not tools_list:
        logger.info("No tools block found or no valid tool lines in Jenkinsfile.groovy.")
        return {}
    if scope == "global":
        # 生成对应的 GitHub Actions steps
        github_actions_steps = generate_yaml_for_tools_by_jobs(tools_list)
        jenkins_comparison = JenkinsComparisonSingle()
        jenkins_comparison.add_comparison(yaml_to_string(github_actions_steps), 'tools', scope)
    else:
        github_actions_steps = generate_yaml_for_tools_by_steps(tools_list)
    return github_actions_steps

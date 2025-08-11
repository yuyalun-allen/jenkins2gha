import re
from converter.utils.normalize_job_name import normalize_identifier


def analyze_jenkins_dependencies(content):
    """
    分析Jenkinsfile，以提取阶段之间的依赖关系，正确处理嵌套stage、parallel和matrix结构。
    """
    # 查找文件中所有stage及其位置
    stage_pattern = r'stage\s*\(\s*[\'"]([^\'"]+)[\'"]'
    stages = []

    for match in re.finditer(stage_pattern, content):
        stage_name = match.group(1)
        position = match.start()
        stages.append((stage_name, position))

    # 找出并行块容器
    parallel_containers = []
    parallel_pattern = r'stage\s*\(\s*[\'"](.*?)[\'"]\s*\)\s*\{[^{}]*?parallel\s*\{'

    for match in re.finditer(parallel_pattern, content):
        container_name = match.group(1)
        container_pos = match.start()
        parallel_start = match.end()

        # 找出parallel块的结束括号
        brace_count = 1
        pos = parallel_start

        while pos < len(content) and brace_count > 0:
            if content[pos] == '{':
                brace_count += 1
            elif content[pos] == '}':
                brace_count -= 1
            pos += 1

        container_end = pos

        # 找出并行块中的阶段
        block_stages = []
        for name, position in stages:
            if parallel_start < position < container_end and name != container_name:
                block_stages.append((name, position))

        if block_stages:
            # 存储容器名称、位置、结束位置和子阶段
            parallel_containers.append(
                (container_name, container_pos, container_end, [name for name, _ in block_stages]))

    # 找出嵌套stages块容器
    nested_stages_containers = []
    nested_stages_pattern = r'stage\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)\s*\{\s*(?:[^{}]*\{[^{}]*\})*[^{}]*stages\s*\{'

    for match in re.finditer(nested_stages_pattern, content):
        container_name = match.group(1)
        container_pos = match.start()
        nested_start = match.end()

        # 找出stages块的结束括号
        brace_count = 1
        pos = nested_start

        while pos < len(content) and brace_count > 0:
            if content[pos] == '{':
                brace_count += 1
            elif content[pos] == '}':
                brace_count -= 1
            pos += 1

        container_end = pos

        # 找出嵌套stages块中的阶段
        nested_stages = []
        for name, position in stages:
            if nested_start < position < container_end and name != container_name:
                nested_stages.append(name)

        if nested_stages:
            nested_stages_containers.append((container_name, container_pos, container_end, nested_stages))

    # 找出矩阵块及其内部阶段
    matrix_containers = []
    matrix_pattern = r'stage\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)\s*\{\s*matrix\s*\{'

    for match in re.finditer(matrix_pattern, content):
        container_name = match.group(1)
        container_pos = match.start()
        matrix_start = match.end()

        # 找出矩阵块的结束括号
        brace_count = 1
        pos = matrix_start

        while pos < len(content) and brace_count > 0:
            if content[pos] == '{':
                brace_count += 1
            elif content[pos] == '}':
                brace_count -= 1
            pos += 1

        container_end = pos

        # 找出矩阵块中的阶段
        matrix_stages = []
        for name, position in stages:
            if matrix_start < position < container_end and name != container_name:
                matrix_stages.append(name)

        if matrix_stages:
            matrix_containers.append((container_name, container_pos, container_end, matrix_stages))

    # 列出要排除的容器stage（仅parallel和nested容器，不包括matrix容器）
    exclude_containers = []
    for container, _, _, _ in parallel_containers:
        exclude_containers.append(container)
    for container, _, _, _ in nested_stages_containers:
        exclude_containers.append(container)

    # 排除matrix内部的阶段，但保留matrix容器本身
    matrix_inner_stages = []
    matrix_containers_list = []
    for container, _, _, inner_stages in matrix_containers:
        matrix_containers_list.append(container)
        matrix_inner_stages.extend(inner_stages)

    # 确定实际执行阶段
    actual_stages = []

    # 添加所有非容器、非matrix内部阶段
    for name, pos in stages:
        if (name not in exclude_containers and  # 不是parallel或nested容器
                name not in matrix_inner_stages):  # 不是matrix内部阶段
            actual_stages.append((name, pos))

    # 添加并行块内部的阶段
    for _, _, _, parallel_stages in parallel_containers:
        for parallel_stage in parallel_stages:
            stage_pos = next((pos for name, pos in stages if name == parallel_stage), None)
            if stage_pos and (parallel_stage, stage_pos) not in actual_stages:
                actual_stages.append((parallel_stage, stage_pos))

    # 根据位置排序阶段
    actual_stages.sort(key=lambda x: x[1])
    stage_names = [name for name, _ in actual_stages]

    # 初始化依赖字典
    dependencies = {name: [] for name in stage_names}

    # 首先确定每个阶段在哪个并行块内部（如果有）
    stage_to_parallel_container = {}
    for _, _, container_end, parallel_stages in parallel_containers:
        for stage in parallel_stages:
            if stage in stage_names:  # 确保阶段在实际阶段列表中
                stage_to_parallel_container[stage] = (container_end, parallel_stages)

    # 构建依赖关系 - 简化为直接序列依赖
    for i in range(1, len(stage_names)):
        current = stage_names[i]
        prev = stage_names[i - 1]

        # 如果当前阶段在并行块内
        if current in stage_to_parallel_container:
            _, parallel_siblings = stage_to_parallel_container[current]

            # 如果前一个阶段不在同一个并行块，则依赖它
            if prev not in parallel_siblings:
                dependencies[current].append(prev)
            else:
                # 如果前一个阶段在同一个并行块，向前找第一个不在此并行块的阶段
                for j in range(i - 2, -1, -1):
                    if j >= 0 and stage_names[j] not in parallel_siblings:
                        dependencies[current].append(stage_names[j])
                        break

        # 如果前一个阶段在并行块内
        elif prev in stage_to_parallel_container:
            container_end, parallel_siblings = stage_to_parallel_container[prev]

            # 如果所有并行阶段都已经处理过，当前阶段依赖所有并行阶段
            if all(sibling in stage_names[:i] for sibling in parallel_siblings if sibling in stage_names):
                dependencies[current] = [s for s in parallel_siblings if s in stage_names]
            else:
                # 否则仅依赖前一个阶段
                dependencies[current].append(prev)

        # 普通顺序依赖
        else:
            dependencies[current].append(prev)
    new_dependencies = {
        normalize_identifier(job_name): [normalize_identifier(name) for name in name_list]
        for job_name, name_list in dependencies.items()
    }

    return new_dependencies


def convert_dependencies_to_github_actions(dependencies):
    """
    将Jenkins依赖关系转换为GitHub Actions needs格式。
    """
    github_needs = {}

    for job, deps in dependencies.items():
        if deps:  # Only add needs if there are dependencies
            github_needs[job] = {"needs": deps}

    return github_needs


def main():
    """
    解析Jenkinsfile并生成GitHub Actions依赖关系的主函数。
    """
    # 示例用法
    jenkinsfile_content = """
pipeline {
    agent any
    stages {
        stage('Initialize') {
            steps {
                echo 'Initializing the pipeline'
            }
        }
        stage('Build') {
            steps {
                echo 'Building the project'
            }
        }
        stage('First Parallel Block') {
            parallel {
                stage('Unit Tests') {
                    steps {
                        echo 'Running unit tests'
                    }
                }
                stage('Static Analysis') {
                    steps {
                        echo 'Running static code analysis'
                    }
                }
                stage('Security Scan') {
                    steps {
                        echo 'Scanning for security vulnerabilities'
                    }
                }
            }
        }
        stage('Integration Tests') {
            steps {
                echo 'Running integration tests'
            }
        }
        stage('Complex Parallel') {
            parallel {
                stage('API Tests') {
                    steps {
                        echo 'Running API tests'
                    }
                }
                stage('UI Tests') {
                    steps {
                        echo 'Running UI tests'
                    }
                }
            }
        }
        stage('Pre-Deploy Checks') {
            steps {
                echo 'Final checks before deployment'
            }
        }
        stage('Final Parallel') {
            parallel {
                stage('Deploy to Staging') {
                    steps {
                        echo 'Deploying to staging environment'
                    }
                }
                stage('Documentation') {
                    steps {
                        echo 'Generating documentation'
                    }
                }
            }
        }
        stage('BuildAndTest') {
            matrix {
                axes {
                    axis {
                        name 'PLATFORM'
                        values 'linux', 'windows', 'mac'
                    }
                    axis {
                        name 'BROWSER'
                        values 'firefox', 'chrome', 'safari', 'edge'
                    }
                }
                excludes {
                    exclude {
                        axis {
                            name 'PLATFORM'
                            notValues 'windows'
                        }
                        axis {
                            name 'BROWSER'
                            values 'edge'
                        }
                    }
                }
                stages {
                    stage('Build6666666666') {
                        steps {
                            echo "Do Build for ${PLATFORM} - ${BROWSER}"
                        }
                    }
                    stage('Test666666666666') {
                        steps {
                            echo "Do Test for ${PLATFORM} - ${BROWSER}"
                        }
                    }
                }
            }
        }
        stage('Final Approval') {
            steps {
                echo 'Waiting for approval'
            }
        }
    }
}
    """

    jenkinsfile_content2 = """
pipeline {
    agent none
    stages {
        stage('Non-Sequential Stage') {
            agent {
                label 'for-non-sequential'
            }
            steps {
                echo "On Non-Sequential Stage"
            }
        }
        stage('Sequential') {
            agent {
                label 'for-sequential'
            }
            environment {
                FOR_SEQUENTIAL = "some-value"
            }
            stages {
                stage('In Sequential 1') {
                    steps {
                        echo "In Sequential 1"
                    }
                }
                stage('In Sequential 2') {
                    steps {
                        echo "In Sequential 2"
                    }
                }
                stage('Parallel In Sequential') {
                    parallel {
                        stage('In Parallel 1') {
                            steps {
                                echo "In Parallel 1"
                            }
                        }
                        stage('In Parallel 2') {
                            steps {
                                echo "In Parallel 2"
                            }
                        }
                    }
                }
                stage('In Sequential 3') {
                    steps {
                        echo "In Sequential 3"
                    }
                }
            }
        }
    }
}
        """

    # 分析依赖关系
    dependencies = analyze_jenkins_dependencies(jenkinsfile_content2)
    print("Extracted dependencies:")
    for stage, deps in dependencies.items():
        print(f"{stage}: {deps}")

    # 转换为GitHub Actions格式
    github_needs = convert_dependencies_to_github_actions(dependencies)
    print("\nGitHub Actions needs:")
    for job, config in sorted(github_needs.items()):
        print(f"{job}: {config}")


if __name__ == "__main__":
    main()
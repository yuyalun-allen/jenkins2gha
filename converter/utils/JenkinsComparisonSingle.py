import threading
from converter.utils.extract_block import extract_block
import re
from converter.utils.find_matching_brace import find_matching_brace
from converter.utils.getLogger import setup_logging

logger = setup_logging()


class JenkinsComparisonSingle:
    """单例类，用于收集 Jenkins 与 GitHub Actions 的对比信息。"""

    _instance = None  # 静态私有变量，保存唯一实例
    _lock = threading.Lock()  # 添加线程锁

    def __new__(cls):
        """实现单例模式，如果实例不存在则创建，否则直接返回已创建的实例。"""
        with cls._lock:  # 使用线程锁确保线程安全
            if cls._instance is None:
                cls._instance = super(JenkinsComparisonSingle, cls).__new__(cls)
                cls._instance._detailed_comparison = []  # 初始化对比列表
                cls._instance._jenkinsfile_content = None  # 初始化 jenkinsfile_content
        return cls._instance

    def __init__(self):
        """初始化方法，由于使用单例模式，仅在首次创建实例时执行初始化。"""
        # 不要在这里重新初始化_detailed_comparison
        pass

    def set_jenkinsfile_content(self, content):
        """
        设置 jenkinsfile 内容，只能在第一次调用时成功设置。

        Args:
            content: 需要设置的 Jenkinsfile 内容

        Returns:
            bool: 设置成功返回 True，否则返回 False
        """
        with self._lock:  # 使用线程锁确保线程安全
            if self._jenkinsfile_content is None:
                self._jenkinsfile_content = content
                return True
            return False

    def get_jenkinsfile_content(self):
        """
        获取保存的 Jenkinsfile 内容。

        Returns:
            保存的 Jenkinsfile 内容，如果未设置则返回 None
        """
        return self._jenkinsfile_content

    def add_comparison(self, string_yaml: str, jenkins_block_name: str, scope="global") -> None:
        """
        新增一条对比记录，每个记录包含: {"jenkins": ..., "actions": ...}
        """
        self._detailed_comparison.append({
            "jenkins": self.extract_complete_block_with_normalized_indentation(None, jenkins_block_name,
                                                                               scope),
            "actions": string_yaml
        })

    def get_comparison(self) -> list:
        """
        返回当前收集到的所有对比信息，列表形式:
        [
          {"jenkins": "...", "actions": "..."},
          ...
        ]
        """
        return self._detailed_comparison

    def clear(self) -> None:
        """
        清空所有收集到的对比信息。
        如果需要在下一次使用前重置，可以调用此方法。
        """
        # self._detailed_comparison.clear()  # 使用clear方法而不是创建新列表
        self._detailed_comparison = []  # 初始化对比列表
        self._jenkinsfile_content = None

    def extract_complete_block(self, content: str = None, block_name: str = None) -> str:
        """提取包含块名称和完整大括号结构的块内容"""
        # 如果未提供内容，使用类中存储的 jenkinsfile_content
        if content is None:
            content = self._jenkinsfile_content
            if content is None:
                logger.warning("No jenkinsfile content has been set.")
                return ""

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

    def extract_complete_block_by_scope(self, content: str = None, block_name: str = None, scope="global") -> str:
        """
        根据指定的作用域提取块内容

        参数:
            content: 要解析的内容 (可选，默认使用类中的 _jenkinsfile_content)
            block_name: 要提取的块名称（如'tools', 'post', 'environment'等）
            scope: 解析范围 - "global"表示Pipeline级别, "stage"表示Stage级别

        返回:
            提取的块内容，如果找不到则返回空字符串
        """
        # 如果未提供内容，使用类中存储的 jenkinsfile_content
        if content is None:
            content = self._jenkinsfile_content
            if content is None:
                logger.warning("No jenkinsfile content has been set.")
                return ""

        # 处理block_name，创建同时支持单引号和双引号的版本
        alternate_block_name = None
        if block_name and block_name.startswith('stage(\'') and block_name.endswith('\')'):
            # 从stage('xxx')提取xxx
            stage_name = block_name[7:-2]
            # 创建支持双引号的alternative：stage("xxx")
            alternate_block_name = f'stage("{stage_name}")'

        if scope == "stage":
            # 已经在stage块内，直接提取指定块
            block_content = self.extract_complete_block(content, block_name)
            # 如果找不到并且存在替代名称，尝试使用替代名称
            if not block_content and alternate_block_name:
                block_content = self.extract_complete_block(content, alternate_block_name)
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
                        block_content = self.extract_complete_block(pipeline_without_stages, block_name)
                        # 如果找不到并且存在替代名称，尝试使用替代名称
                        if not block_content and alternate_block_name:
                            block_content = self.extract_complete_block(pipeline_without_stages, alternate_block_name)
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
                block_content = self.extract_complete_block(pipeline_content, block_name)
                # 如果找不到并且存在替代名称，尝试使用替代名称
                if not block_content and alternate_block_name:
                    block_content = self.extract_complete_block(pipeline_content, alternate_block_name)
                if not block_content:
                    logger.info(f"No global {block_name} block found.")
                    return ""
                return block_content

    def extract_complete_block_with_normalized_indentation(self, content: str = None, block_name: str = None,
                                                           scope="global") -> str:
        """
        提取块内容并规范化缩进

        参数:
            content: 要解析的内容 (可选，默认使用类中的 _jenkinsfile_content)
            block_name: 要提取的块名称
            scope: 解析范围 - "global"表示Pipeline级别, "stage"表示Stage级别

        返回:
            已提取且缩进规范化的块内容
        """
        # 如果未提供内容，使用类中存储的 jenkinsfile_content
        if content is None:
            content = self._jenkinsfile_content
            if content is None:
                logger.warning("No jenkinsfile content has been set.")
                return ""

        # 首先使用现有函数提取块
        extracted_block = self.extract_complete_block_by_scope(content, block_name, scope)

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

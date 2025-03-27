import re
from converter.utils.extract_block import extract_block
from converter.utils.find_matching_brace import find_matching_brace
from converter.utils.getLogger import setup_logging

logger = setup_logging()


def extract_block_by_scope(content: str, block_name: str, scope="global") -> str:
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
        block_content = extract_block(content, block_name)
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
                    block_content = extract_block(pipeline_without_stages, block_name)
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
            block_content = extract_block(pipeline_content, block_name)
            if not block_content:
                logger.info(f"No global {block_name} block found.")
                return ""
            return block_content

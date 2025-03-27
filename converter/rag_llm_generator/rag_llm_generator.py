import numpy as np
from converter.rag_llm_generator.vectorization.vectorizer import vectorize_text
from converter.rag_llm_generator.vectorization.faiss_indexer import create_faiss_index, save_faiss_index, load_faiss_index
from converter.rag_llm_generator.vectorization.search import search_faiss_index
from converter.rag_llm_generator.rag_utils.file_reader import process_plugin_data
from converter.rag_llm_generator.rag_utils.queryLLM import construct_prompt, query_llm
from converter.utils.getLogger import setup_logging

logger = setup_logging()


def generate_github_actions(jenkins_config):
    # 创建或加载 FAISS 索引
    index = load_faiss_index()
    if index is None:
        logger.info("创建新的 FAISS 索引...")
        # 加载插件数据
        logger.info("加载插件数据...")
        plugin_data = process_plugin_data()

        # 向量化插件数据
        logger.info("向量化插件数据...")
        vectors = vectorize_text(plugin_data)

        index = create_faiss_index(np.array(vectors))  # 创建新索引
        save_faiss_index(index)  # 保存索引
    else:
        logger.info("加载现有的 FAISS 索引...")

    if jenkins_config is None:
        logger.warning("未能读取 unmatched.json，程序终止。")
        return

    # 向量化 Jenkins 配置
    logger.info("向量化 Jenkins 配置...")
    query_vector = vectorize_text([jenkins_config])

    # 在 FAISS 索引中搜索最相似的插件描述
    logger.info("在 FAISS 索引中搜索最相似的插件描述...")
    distances, indices = search_faiss_index(query_vector, index, top_k=3)

    if indices[0][0] == -1:
        logger.warning("未找到相似的插件描述，程序终止。")
        return

    # 输出最相似的结果
    logger.info("最相似的插件信息：")
    plugin_data = process_plugin_data()
    for i, idx in enumerate(indices[0]):
        # 将插件数据分割成行，并只取前3行
        data_lines = str(plugin_data[idx]).split('\n')
        max_lines = 3

        if len(data_lines) > max_lines:
            truncated_data = '\n'.join(data_lines[:max_lines]) + '\n...'
        else:
            truncated_data = str(plugin_data[idx])

        logger.info(f"Rank {i + 1}: {truncated_data} \n (Distance: {distances[0][i]:.4f})")
    # for i, idx in enumerate(indices[0]):
    #     logger.info(f"Rank {i + 1}: {plugin_data[idx]} \n (Distance: {distances[0][i]:.4f})")

    similar_plugin = plugin_data[indices[0][0]]
    plugin_description = similar_plugin  # 假设 plugin_data 中存储的是描述文本

    logger.info(f"找到最相似的插件描述 (距离: {distances[0][0]:.4f})")

    # 构建提示内容
    logger.info("构建提示内容...")
    prompt = construct_prompt(jenkins_config, plugin_description)

    # 调用 LLM 生成 GitHub Actions 配置
    logger.info("调用 LLM 生成 GitHub Actions 配置...")
    github_actions_yaml = query_llm(prompt)

    # 输出结果
    logger.info(f"====== 生成的 GitHub Actions YAML 配置如下 =====\n{github_actions_yaml}")
    # logger.info(github_actions_yaml)

    # print("\nGitHub Actions YAML 配置已保存到 github_actions.yaml")
    return github_actions_yaml

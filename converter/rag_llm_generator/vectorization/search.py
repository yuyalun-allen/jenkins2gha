# 从 FAISS 索引中进行搜索
def search_faiss_index(query_vector, index, top_k=3):
    """
    在 FAISS 索引中进行查询，返回最相似的前 K 个结果。
    :param query_vector: 查询文本的向量
    :param index: FAISS 索引
    :param top_k: 返回最相似的前 K 个结果
    :return: 最相似的文本及其索引
    """
    # 搜索最相似的向量，返回距离和索引
    distances, indices = index.search(query_vector, top_k)
    return distances, indices

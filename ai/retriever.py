def retrieve_context(
    question: str,
    module: str = "buyer",
    state: str = "MA",
    program: str = "medical",
    n_results: int = 5,
):
    _ = (question, module, state, program, n_results)
    return {"documents": [[]], "metadatas": [[]]}

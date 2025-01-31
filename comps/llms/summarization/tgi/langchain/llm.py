# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os

from fastapi.responses import StreamingResponse
from langchain.chains.summarize import load_summarize_chain
from langchain.docstore.document import Document
from langchain.text_splitter import CharacterTextSplitter
from langchain_huggingface import HuggingFaceEndpoint

from comps import CustomLogger, GeneratedDoc, LLMParamsDoc, ServiceType, opea_microservices, register_microservice

logger = CustomLogger("llm_docsum")
logflag = os.getenv("LOGFLAG", False)


def post_process_text(text: str):
    if text == " ":
        return "data: @#$\n\n"
    if text == "\n":
        return "data: <br/>\n\n"
    if text.isspace():
        return None
    new_text = text.replace(" ", "@#$")
    return f"data: {new_text}\n\n"


@register_microservice(
    name="opea_service@llm_docsum",
    service_type=ServiceType.LLM,
    endpoint="/v1/chat/docsum",
    host="0.0.0.0",
    port=9000,
    llm_endpoint=os.getenv("TGI_LLM_ENDPOINT", "http://localhost:8080"),
)
async def llm_generate(input: LLMParamsDoc):
    if logflag:
        logger.info(input)

    llm = HuggingFaceEndpoint(
        endpoint_url=llm_endpoint,
        max_new_tokens=input.max_tokens,
        top_k=input.top_k,
        top_p=input.top_p,
        typical_p=input.typical_p,
        temperature=input.temperature,
        repetition_penalty=input.repetition_penalty,
        streaming=input.streaming,
    )
    llm_chain = load_summarize_chain(llm=llm, chain_type="map_reduce")
    texts = text_splitter.split_text(input.query)

    # Create multiple documents
    docs = [Document(page_content=t) for t in texts]

    if input.streaming:

        async def stream_generator():
            from langserve.serialization import WellKnownLCSerializer

            _serializer = WellKnownLCSerializer()
            async for chunk in llm_chain.astream_log(docs):
                data = _serializer.dumps({"ops": chunk.ops}).decode("utf-8")
                if logflag:
                    logger.info(f"[docsum - text_summarize] data: {data}")
                yield f"data: {data}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    else:
        response = await llm_chain.ainvoke(docs)
        response = response["output_text"]
        if logflag:
            logger.info(response)
        return GeneratedDoc(text=response, prompt=input.query)


if __name__ == "__main__":
    llm_endpoint = os.getenv("TGI_LLM_ENDPOINT", "http://localhost:8080")
    # Split text
    text_splitter = CharacterTextSplitter()
    opea_microservices["opea_service@llm_docsum"].start()

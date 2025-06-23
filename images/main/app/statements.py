from ockam import Agent, Model, Node

from asyncio import gather, create_task
from json import loads
from typing import List, Dict

from .box import Box


async def analyze(node: Node, file: str, model: str):
    agent = await Agent.start(
        node=node,
        instructions="""
            You are an agent who specializes in extracting information
            from business bank statements.

            When you're given the markdown of a bank statement.
                Extract the following fields:
                    1. Last four digits of account number.
                    2. Month of the statement.
                    3. Year of the statement.
        """,
        model=Model(
            name=model,
            response_format={
                "type": "json_object",
                "response_schema": {
                    "type": "object",
                    "properties": {
                        "last_four_digits_of_account_number": {"type": "string"},
                        "month": {"type": "string"},
                        "year": {"type": "string"},
                    },
                    "required": [
                        "last_four_digits_of_account_number",
                        "month",
                        "year",
                    ],
                },
            },
        ),
    )

    response = await agent.send(f"Bank Statement:\n\n{file}", timeout=1000)
    analysis = loads(response[0].content)
    create_task(Agent.stop(node, agent.name))
    return analysis


async def analyze_statement(node: Node, box: Box, file: str) -> dict:
    try:
        extracted = await box.extract(file)
        a1, a2 = await gather(
            analyze(node, extracted, "llama4-scout"),
            analyze(node, extracted, "nova-pro-v1"),
        )

        # renamed = box.client.files.update_file_by_id(file, name="new-name.pdf")
        return {"box_file_id": file, "analysis": a1, "needs_human_review": a1 != a2}
    except Exception as e:
        return {"box_file_id": file, "error": str(e)}


async def analyze_statements(node: Node, box: Box, files: List[str]) -> Dict[str, str]:
    futures = [analyze_statement(node, box, file) for file in files]
    return await gather(*futures)


async def list_statements(box: Box, customer: str):
    files = []
    for i in box.client.folders.get_folder_items("0").entries:
        if i.name == "bank_statements":
            for j in box.client.folders.get_folder_items(i.id).entries:
                if j.name == customer:
                    for k in box.client.folders.get_folder_items(j.id).entries:
                        files.append(k.id)
    return files

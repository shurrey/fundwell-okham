from ockam import HttpServer, Node

from fastapi import FastAPI, HTTPException, status, Security
from fastapi.security.api_key import APIKeyQuery

from dataclasses import dataclass
from os import environ
from typing import Dict, List, Union

from .box import Box
from .statements import list_statements, analyze_statements


class App:
    def __init__(self):
        self.api = FastAPI()

    def routes(self, node: Node):
        app = self.api
        api_key_env = environ["API_KEY"]
        api_key_query = APIKeyQuery(name="api_key", auto_error=False)
        box = Box()

        def key(api_key_query: str = Security(api_key_query)) -> str:
            if api_key_query != api_key_env:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Please provide a valid API key.",
                )
            return api_key_query

        @dataclass
        class GetAnalysisOfBankStatementsResponse:
            analysis: List[Dict[str, Union[dict, str, bool]]]

        @app.get(
            "/analysis_of_bank_statements",
            response_model=GetAnalysisOfBankStatementsResponse,
        )
        async def get_analysis_of_bank_statements(
            box_file_ids: str, key: str = Security(key)
        ) -> GetAnalysisOfBankStatementsResponse:
            box_file_ids_list = box_file_ids.split(",")
            analysis = await analyze_statements(node, box, box_file_ids_list)
            return GetAnalysisOfBankStatementsResponse(analysis)

        @dataclass
        class GetBankStatementsResponse:
            bank_statements: List[str]

        @app.get("/bank_statements")
        async def get_bank_statements(
            customer: str, key: str = Security(key)
        ) -> GetBankStatementsResponse:
            statements = await list_statements(box, customer)
            return GetBankStatementsResponse(bank_statements=statements)


Node.start(http_server=HttpServer(api=App()))

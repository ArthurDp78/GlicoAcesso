from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def entrada_invalida_400(app: FastAPI, *caminhos: str) -> None:
    """Responde 400 nas operações cujo contrato documenta esse código; as demais mantêm o 422 do FastAPI."""
    @app.exception_handler(RequestValidationError)
    async def responder(request: Request, erro: RequestValidationError):
        if getattr(request.scope.get("route"), "path", None) not in caminhos:
            return await request_validation_exception_handler(request, erro)
        campos = ", ".join(sorted({".".join(str(parte) for parte in item["loc"]) for item in erro.errors()}))
        return JSONResponse({"codigo": "ENTRADA_INVALIDA", "mensagem": f"Entrada inválida: {campos}."}, status_code=400)

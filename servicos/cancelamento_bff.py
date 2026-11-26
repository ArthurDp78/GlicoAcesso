from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

from servicos.http import requisitar


async def cancelar_pelo_bff(
    request: Request, reservas: str, orquestrador: str, rota: str, acompanhamento: str,
    reserva_id, chave: str, credencial_delegada, corpo: dict | None = None,
) -> Response:
    cliente = request.app.state.http
    resposta = await requisitar(
        cliente, "POST", reservas + rota,
        headers={"Authorization": request.headers["authorization"], "Idempotency-Key": chave},
        json=corpo,
    )
    if resposta.status_code == 409:
        try:
            encaminhar = resposta.json().get("codigo") == "CANCELAMENTO_DISTRIBUIDO"
        except (ValueError, AttributeError):
            encaminhar = False
        if encaminhar:
            resposta = await requisitar(
                cliente, "POST", f"{orquestrador}/internal/v1/reservas/{reserva_id}/cancelamentos",
                headers={"Authorization": "Bearer " + credencial_delegada(), "Idempotency-Key": chave},
                json=corpo,
            )
    if resposta.status_code == 202:
        return JSONResponse({"reservaId": str(reserva_id)}, status_code=202,
                            headers={"Location": acompanhamento, "Cache-Control": "no-store"})
    if resposta.status_code not in (200, 401, 403, 404, 409, 422, 502, 503, 504):
        raise HTTPException(502, "Resposta inesperada no cancelamento.")
    headers = {"Cache-Control": "no-store"}
    if "WWW-Authenticate" in resposta.headers:
        headers["WWW-Authenticate"] = resposta.headers["WWW-Authenticate"]
    return Response(resposta.content, status_code=resposta.status_code, media_type="application/json", headers=headers)

"""Cria ou completa o .env local com credenciais distintas, sem imprimi-las."""
import argparse
import os
import re
import secrets
from pathlib import Path


def configurar(raiz: Path, arquivo: Path, verificar: bool) -> None:
    modelo = (raiz / ".env.example").read_text(encoding="utf-8").splitlines()
    padrao = re.compile(r"^([A-Z_][A-Z_0-9]*)=(.*)$")
    campos = dict(padrao.fullmatch(linha).groups() for linha in modelo if padrao.fullmatch(linha))
    obrigatorios = {nome for nome, valor in campos.items() if not valor}
    linhas = arquivo.read_text(encoding="utf-8-sig").splitlines() if arquivo.exists() else []
    existentes = {}
    for linha in linhas:
        campo = padrao.fullmatch(linha)
        if campo and campo[1] in campos:
            if campo[1] in existentes:
                raise ValueError(f"{campo[1]} está definido mais de uma vez em {arquivo.name}.")
            existentes[campo[1]] = campo[2]

    credenciais = {}
    for nome in sorted(obrigatorios):
        valor = os.environ.get(nome, existentes.get(nome, ""))
        if not valor and not verificar and nome not in os.environ:
            valor = secrets.token_hex(32)
        if not re.fullmatch(r"[!-~]{32,}", valor) or any(c in valor for c in "'\"$#\\"):
            raise ValueError(f"Configure {nome} com pelo menos 32 caracteres compatíveis com o .env.")
        if (nome.startswith("POSTGRES_") or nome == "RABBITMQ_PASSWORD") and not re.fullmatch(r"[0-9a-fA-F]+", valor):
            raise ValueError(f"Use uma senha hexadecimal em {nome}.")
        credenciais[nome] = valor
    if len(set(credenciais.values())) != len(credenciais):
        raise ValueError("Configure uma credencial diferente para cada campo de senha ou token.")

    if not verificar:
        substituicoes = {
            nome: valor for nome, valor in credenciais.items()
            if not existentes.get(nome) and nome not in os.environ
        }
        atualizadas = [
            f"{campo[1]}={substituicoes[campo[1]]}" if (campo := padrao.fullmatch(linha))
            and campo[1] in substituicoes else linha for linha in linhas
        ]
        if not linhas:
            atualizadas = [linha for linha in modelo if linha.startswith("#")]
        for nome, valor in campos.items():
            if nome not in existentes and (nome in substituicoes or nome not in obrigatorios):
                atualizadas.append(f"{nome}={substituicoes.get(nome, valor)}")
        if atualizadas != linhas:
            # O arquivo temporário e o final têm acesso exclusivo do usuário em POSIX.
            temporario = arquivo.with_name(f".{arquivo.name}.{secrets.token_hex(8)}")
            try:
                with os.fdopen(os.open(temporario, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
                               "w", encoding="utf-8") as destino:
                    destino.write("\n".join(atualizadas) + "\n")
                temporario.replace(arquivo)
            finally:
                temporario.unlink(missing_ok=True)


if __name__ == "__main__":
    raiz = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arquivo", type=Path, default=raiz / ".env")
    parser.add_argument("--verificar", action="store_true")
    args = parser.parse_args()
    try:
        configurar(raiz, args.arquivo, args.verificar)
    except (OSError, ValueError) as erro:
        parser.exit(1, f"{erro}\n")

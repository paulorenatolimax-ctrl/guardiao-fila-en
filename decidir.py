#!/usr/bin/env python3
"""03/10/2026: regra de RECUPERAÇÃO (catch-up) para os 3 tipos de post.

O cron do GitHub atrasa e pula execuções; a regra antiga de "janela" fazia o post
atrasado ser PULADO. Agora, a cada execução (cron a cada 5 min, 7h-23h59 BRT):

  1. conta quantos horários do dia já venceram (ex.: carrossel às 14h -> 8h e 11h = 2);
  2. conta quantos posts daquele tipo saíram HOJE (BRT; "publicado" é gravado em UTC);
  3. se publicados < vencidos, publica o próximo da fila, desde que:
       - o último post daquele tipo tenha saído há pelo menos INTERVALO (90 min / 4 h);
       - agora esteja entre 7h00 e 23h59 BRT;
       - não passe do MÁXIMO do dia;
     e nunca mais de 1 por execução (cada execução publica no máximo 1 item).

'forcar' (disparo manual com a caixa marcada) publica sem regra nenhuma.
Disparo manual SEM 'forcar' segue a mesma regra do cron (é o que o Mac usa).

Uso no workflow:  python3 decidir.py reel|carrossel|teste   -> grava deve_publicar=true/false
"""
import json, os, sys
from datetime import date, datetime, timedelta, timezone

# CONTA EM INGLÊS. 22/11/2026 11h20 (Paulo): "É 5 por dia. Pode começar com 3 na primeira semana, depois vai aumentar para 5 ou 6."
# 22/11 a 28/11: 3 por dia (9h, 13h, 18h BRT). De 29/11 em diante: 5 por dia (8h, 11h, 14h, 17h, 20h BRT).
_SEMANA1 = ([9, 13, 18], timedelta(minutes=90), 3)
_DEPOIS = ([8, 11, 14, 17, 20], timedelta(minutes=90), 5)
_g = _SEMANA1 if (datetime.now(timezone.utc) - timedelta(hours=3)).date() < date(2026, 11, 29) else _DEPOIS
TIPOS = {
    "carrossel": ("carrosseis.json", "carrosseis", _g[0], _g[1], _g[2]),
}
ESPECIAIS = {}
INICIO_DIA = 7  # nada sai antes das 7h BRT (e o cron vai até 23h59 BRT)


def brt_agora():
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=3)


def utc_para_brt(texto):
    return datetime.strptime(texto, "%Y-%m-%d %H:%M") - timedelta(hours=3)


def decidir(tipo, agora_brt, itens, forcar=False):
    """Função pura. Devolve (deve_publicar, motivo).
    itens = lista do JSON (cada um com "publicado" em UTC 'AAAA-MM-DD HH:MM' ou vazio)."""
    _, _, horarios, intervalo, maximo = TIPOS[tipo]
    horarios, intervalo, maximo = ESPECIAIS.get(tipo, {}).get(agora_brt.date(), (horarios, intervalo, maximo))
    if not any(not x.get("publicado") for x in itens):
        return False, f"[{tipo}] fila vazia"
    # 21/10/2026: trava de pausa (Paulo: "não sobe mais nenhum carrossel hoje"). Vale até para o forçado.
    # Arquivo PAUSA_<tipo> com a data-hora BRT "AAAA-MM-DD HH:MM" até quando nada sai.
    import os as _os
    _pa = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), f"PAUSA_{tipo}")
    if _os.path.exists(_pa):
        _ate = datetime.strptime(open(_pa).read().strip(), "%Y-%m-%d %H:%M")
        if agora_brt.replace(tzinfo=None) < _ate:
            return False, f"[{tipo}] PAUSA: nada sai até {_ate:%d/%m %H:%M} BRT (arquivo PAUSA_{tipo})"
    if forcar:
        # 20/10/2026: Lennon (G298) e a palavra saíram com 2 min de diferença e um comeu o outro.
        # Nem o forçado sai se outro do mesmo tipo saiu há menos de 30 min.
        pubs = [utc_para_brt(x["publicado"]) for x in itens if x.get("publicado") and not x.get("excluido_pelo_paulo")]  # 30/10: post apagado pelo Paulo não trava o próximo
        ultimo = max(pubs) if pubs else None
        if ultimo and timedelta(0) <= agora_brt - ultimo < timedelta(minutes=30):
            return False, f"[{tipo}] FORCAR barrado: o último saiu às {ultimo:%H:%M} BRT, menos de 30 min atrás"
        return True, f"[{tipo}] FORCAR: publicando sem regras"

    if agora_brt.hour < INICIO_DIA:
        return False, f"[{tipo}] {agora_brt:%H:%M} BRT: antes das {INICIO_DIA}h, nada sai"

    pubs = [utc_para_brt(x["publicado"]) for x in itens if x.get("publicado")]
    hoje = agora_brt.date()
    feitos = sum(1 for p in pubs if p.date() == hoje)
    vencidos = sum(1 for h in horarios if h * 60 <= agora_brt.hour * 60 + agora_brt.minute)

    if feitos >= maximo:
        return False, f"[{tipo}] já saíram {feitos} hoje (máximo {maximo})"
    if feitos >= vencidos:
        return False, f"[{tipo}] {agora_brt:%H:%M} BRT: {feitos} publicados / {vencidos} horários vencidos: em dia"
    ultimo = max(pubs) if pubs else None
    if ultimo and agora_brt - ultimo < intervalo:
        falta = intervalo - (agora_brt - ultimo)
        return False, (f"[{tipo}] atrasado ({feitos}/{vencidos}), mas o último saiu às {ultimo:%d/%m %H:%M} BRT; "
                       f"espera mais {int(falta.total_seconds() // 60)} min")
    return True, f"[{tipo}] {agora_brt:%H:%M} BRT: {feitos} publicados / {vencidos} vencidos: publicando 1"


MAX_SLIDES = 10  # limite da API do Instagram para carrossel


def proximo_valido(itens, max_slides=MAX_SLIDES):
    """Primeiro item não publicado com <= max_slides slides. Retorna (item|None, [mensagens de pulo])."""
    logs = []
    # trava contra duplicata (04/10/2026: o carrossel de dados saiu 2x porque foi recolocado na fila
    # já publicado): mesmas imagens ou mesmo título de um item já publicado = pula
    ja = [x for x in itens if x.get("publicado")]
    ja_slides = {tuple(x.get("slides", [])) for x in ja}
    ja_titulos = {(x.get("titulo") or "").strip().lower() for x in ja}
    for c in itens:
        if c.get("publicado"):
            continue
        if tuple(c.get("slides", [])) in ja_slides or (c.get("titulo") or "").strip().lower() in ja_titulos:
            logs.append(f"PULADO {c.get('id')}: já publicado antes (mesmas imagens ou mesmo título)")
            continue
        # trava do OK (04/10/2026): o Paulo vê cada carrossel antes. Sem "aprovado": true, nunca sai (nem com forcar).
        if "slides" in c and not c.get("aprovado"):
            logs.append(f"PULADO {c.get('id')}: ainda sem o OK do Paulo (falta \"aprovado\": true)")
            continue
        n = len(c.get("slides", []))
        if n > max_slides:
            logs.append(f"PULADO {c.get('id')}: {n} slides (máximo {max_slides} no Instagram)")
            continue
        return c, logs
    return None, logs


def main():
    tipo = sys.argv[1] if len(sys.argv) > 1 else "reel"
    arquivo, chave = TIPOS[tipo][0], TIPOS[tipo][1]
    itens = json.load(open(arquivo))[chave]
    forcar = (os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
              and os.environ.get("FORCAR", "false") == "true")
    ok, motivo = decidir(tipo, brt_agora(), itens, forcar)
    print(motivo)
    saida = os.environ.get("GITHUB_OUTPUT")
    if saida:
        with open(saida, "a") as f:
            f.write(f"deve_publicar={'true' if ok else 'false'}\n")


if __name__ == "__main__":
    main()

# Service autonome de Perlecta : une image, un point d'entree, aucun etat.
#
# Execution recommandee, sans privileges et en lecture seule :
#   docker run --rm --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
#     --cap-drop ALL --security-opt no-new-privileges --pids-limit 64 \
#     --memory 2g -p 8123:8123 perlecta
#
# --pids-limit est le plafond du nombre de processus : il releve du conteneur,
# pas des limites posees par le sous-processus confine (RLIMIT_NPROC compte
# les processus de l'utilisateur, pas ceux de l'analyse).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --gid 10001 perlecta \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin perlecta

WORKDIR /app
COPY pyproject.toml README.md CONTRAT.md LICENSE NOTICE ./
COPY src ./src
RUN pip install ".[service]" && rm -rf /app/src /root/.cache

USER perlecta
EXPOSE 8123

# Le service n'ecrit rien et ne fait aucune sortie reseau : il ecoute, c'est tout.
ENTRYPOINT ["perlecta", "serve", "--host", "0.0.0.0", "--port", "8123"]

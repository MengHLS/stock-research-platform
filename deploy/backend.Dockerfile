FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY backend ./backend
# 建号/发邀请码走 tools/project.py；镜像内保留该入口，避免部署后无法创建首个账号。
COPY tools ./tools
RUN uv sync --frozen --no-dev --no-editable && useradd --create-home appuser && mkdir .scratch && chown appuser .scratch
ENV PATH="/app/.venv/bin:$PATH"
USER appuser
EXPOSE 8000
CMD ["uvicorn", "research_platform.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

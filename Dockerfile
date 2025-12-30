FROM python:3.11-slim

WORKDIR /app

# 复制依赖文件（使用事先下载好的 Linux 版离线包）
COPY requirements.docker.txt requirements.txt
COPY python_packages_linux /app/python_packages

# 安装Python依赖（禁用代理避免连接问题）
ENV http_proxy=""
ENV https_proxy=""
ENV no_proxy="*"
RUN pip install --no-cache-dir --no-index --find-links=/app/python_packages -r requirements.txt

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p /app/data

# 暴露端口
EXPOSE 8081

# 启动命令
CMD ["python", "main.py"]

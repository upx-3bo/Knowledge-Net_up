# NebulaGraph 本地环境（AI4KnowledgeNet）

## 连接信息

| 服务 | 地址 |
|------|------|
| Graphd (nGQL) | `localhost:9669` |
| Studio UI | http://localhost:7001 |
| 默认账号 | `root` / 密码为空 |

Studio 连接时 Host 填 `graphd`（容器内）或本机 `host.docker.internal` / 网关 IP，端口 `9669`。从本机浏览器访问 Studio 时，连接地址一般用 `主机局域网 IP:9669`。

## 启动 / 停止

在 Docker 可用后：

```bash
cd infra/nebula
docker compose up -d
docker compose ps
docker compose down
```

首次启动后，进入 graphd 注册 storage：

```bash
docker compose exec graphd nebula-console -addr graphd -port 9669 -u root -p ''
```

在控制台执行：

```ngql
ADD HOSTS "storaged0":9779;
SHOW HOSTS;
```

## 说明

本机为 Windows Server 2022，不支持 Docker Desktop；使用 WSL2 + Docker Engine。

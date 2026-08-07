# NebulaGraph 运行环境安装手册（Windows + Docker Desktop + WSL2）

> 目标：在 Windows 上运行真实的 NebulaGraph 图数据库，供 AI 知识库使用。
>
> **注意**：以下步骤均为**系统级安装**，必须以**管理员身份**执行，且**需要重启电脑**。
> 请按顺序执行，每一步完成后确认无误再进行下一步。

---

## 第 1 步：检查当前状态（普通权限终端即可）

打开 PowerShell（普通权限），运行：

```powershell
wsl --status
docker --version
```

正常情况下应提示"未安装"或找不到命令。若第 2 步执行后仍异常，先看"常见问题"。

---

## 第 2 步：启用 WSL2（需要管理员）

1. **右键** 开始菜单 → 选择 **"终端(管理员)"** 或 **"Windows PowerShell (管理员)"**
2. 在管理员窗口中执行：

```powershell
wsl --install
```

- 该命令会自动启用"适用于 Linux 的 Windows 子系统"和"虚拟机平台"两个功能，
  并默认安装 **Ubuntu** 发行版。
- 执行完成后**必须重启电脑**。

3. 重启后，首次打开 Ubuntu 终端会让你创建 **Linux 用户名和密码**（自己记住）。

4. 验证 WSL2（普通终端）：

```powershell
wsl --version
wsl --list
```

应显示 Ubuntu 已安装，且版本为 **2**。

> 若 `wsl --install` 失败或版本不是 2，执行以下手动启用（仍为管理员）：
> ```powershell
> dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
> dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
> wsl --set-default-version 2
> ```
> 然后重启。

---

## 第 3 步：安装 Docker Desktop（需要管理员）

1. 下载安装包：
   - 官网：https://www.docker.com/products/docker-desktop/
   - 或使用 `winget`（管理员终端）：`winget install Docker.DockerDesktop`

2. 双击安装包，安装时**务必勾选 "Use WSL 2 instead of Hyper-V"**（默认通常已勾选）。

3. 安装完成后**重启电脑**。

4. 打开 **Docker Desktop**（开始菜单搜 "Docker"），等待启动完成，
   右下角状态显示 **"Engine running"** 即成功。

5. 验证（普通终端）：

```powershell
docker --version
docker compose version
```

应显示 Docker 版本号，且能正常输出（不报权限错误）。

---

## 第 4 步：配置公司代理（很重要，否则拉不到镜像）

公司网络走代理 `proxy.huawei.com:8080`，Docker 必须配置代理才能从 Docker Hub 拉取 NebulaGraph 镜像。

1. 打开 **Docker Desktop** → 右上角 **设置(齿轮)** → **Resources → Proxies**
2. 打开 **Manual proxy configuration**
   - HTTP Proxy: `http://proxy.huawei.com:8080`
   - HTTPS Proxy: `http://proxy.huawei.com:8080`
   - 保存并重启 Docker Desktop

3. 测试能否拉取镜像（普通终端）：

```powershell
docker pull hello-world
```

能成功拉取即表示代理配置正确。

---

## 第 5 步：回到知识库项目，拉起 NebulaGraph

代理配置好后，告诉我一声，我会帮你完成：
1. 拉取并启动 NebulaGraph 三组件（graphd/metad/storaged）+ Studio
2. 初始化图 Space 和 Schema
3. 把后端切换到 NebulaGraph 引擎并导入现有 8技术/9分类/6标准 数据

---

## 常见问题

| 现象 | 处理 |
|------|------|
| `wsl --install` 报错 0x800701bc | 需先安装内核更新包，运行 `wsl --update` |
| Docker 提示 WSL 版本为 1 | `wsl --set-default-version 2` |
| docker pull 超时/失败 | 检查第 4 步代理配置是否正确、Docker 是否重启 |
| docker 命令无权限 | 确认你的账号已加入 `docker-users` 组，或重新登录系统 |
| 需要管理员但提示拒绝 | 确保以管理员身份打开终端 |

---

*如遇其他报错，截图或复制报错信息给我，我来帮你排查。*

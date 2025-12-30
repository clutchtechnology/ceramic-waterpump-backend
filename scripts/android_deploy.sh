#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# Android 工控机一键部署脚本 (含 InfluxDB)
# ============================================================
# 功能: 自动安装 InfluxDB + Python 后端
# 使用: bash android_deploy.sh
# ============================================================

set -e  # 遇到错误立即退出

echo "======================================================================"
echo "🚀 陶瓷车间水泵房后端 - Android 部署脚本 (InfluxDB 版本)"
echo "======================================================================"
echo ""

# 检查是否在 Termux 环境
if [ ! -d "/data/data/com.termux" ]; then
    echo "❌ 错误: 此脚本必须在 Termux 环境中运行！"
    echo "请先安装 Termux: https://f-droid.org/packages/com.termux/"
    exit 1
fi

# 1. 更新系统包
echo "📦 [1/8] 更新系统包..."
pkg update -y
pkg upgrade -y

# 2. 安装必要工具
echo "🔧 [2/8] 安装工具 (python, git, openssh)..."
pkg install -y python git openssh wget curl

# 3. 升级 pip
echo "⬆️ [3/10] 升级 pip..."
pip install --upgrade pip

# 4. 安装 InfluxDB
echo "💾 [4/10] 安装 InfluxDB ARM64..."

mkdir -p ~/influxdb
cd ~/influxdb

# 下载 InfluxDB (如果不存在)
if [ ! -f "influxd" ]; then
    echo "  📥 下载 InfluxDB 2.7.10 ARM64..."
    wget -q --show-progress https://dl.influxdata.com/influxdb/releases/influxdb2-2.7.10_linux_arm64.tar.gz
    
    echo "  📦 解压中..."
    tar xzf influxdb2-2.7.10_linux_arm64.tar.gz
    
    mv influxdb2-2.7.10/usr/bin/influxd ./
    mv influxdb2-2.7.10/usr/bin/influx ./
    
    rm -rf influxdb2-2.7.10 influxdb2-2.7.10_linux_arm64.tar.gz
    
    echo "  ✅ InfluxDB 安装完成"
else
    echo "  ✅ InfluxDB 已存在，跳过下载"
fi

# 创建数据目录
mkdir -p data config logs

# 5. 初始化 InfluxDB
echo "⚙️ [5/10] 初始化 InfluxDB..."

if [ ! -f "data/influxd.bolt" ]; then
    # 后台启动 InfluxDB
    ./influxd --bolt-path=./data/influxd.bolt --engine-path=./data/engine --http-bind-address=:8086 > logs/init.log 2>&1 &
    INFLUXD_PID=$!
    
    echo "  ⏳ 等待 InfluxDB 启动 (15秒)..."
    sleep 15
    
    # 初始化配置
    ./influx setup \
        --username admin \
        --password influxdb123456 \
        --org ceramic-workshop \
        --bucket waterpump \
        --force
    
    # 获取 Token
    INFLUX_TOKEN=$(./influx auth list | grep "admin's Token" | awk '{print $4}')
    
    echo "  ✅ InfluxDB 初始化完成"
    echo "  📝 Token: $INFLUX_TOKEN"
    echo "$INFLUX_TOKEN" > config/token.txt
    
    # 停止测试实例
    kill $INFLUXD_PID
    sleep 2
else
    echo "  ✅ InfluxDB 已初始化，跳过"
    INFLUX_TOKEN=$(cat config/token.txt 2>/dev/null || echo "请手动设置")
fi

# 6. 克隆代码仓库
echo "📥 [6/10] 准备代码..."
# 6. 克隆代码仓库
echo "📥 [6/10] 准备代码..."
cd ~

if [ -d "waterpump-backend" ]; then
    echo "⚠️ 目录已存在，正在备份..."
    mv waterpump-backend waterpump-backend.bak.$(date +%Y%m%d_%H%M%S)
fi

# 这里替换为你的 Git 仓库地址
# git clone https://github.com/yourname/ceramic-waterpump-backend.git waterpump-backend

# 如果没有 Git 仓库，手动创建目录结构
echo "⚠️ 请手动上传代码到 ~/waterpump-backend/"
echo "   方法1: 使用向日葵文件传输"
echo "   方法2: 使用 scp 上传"
echo ""
read -p "代码已上传完成？(y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ 部署已取消"
    exit 1
fi

cd ~/waterpump-backend

# 7. 安装 Python 依赖
echo "📚 [7/10] 安装 Python 依赖..."
pip install fastapi uvicorn python-snap7 influxdb-client psutil pyyaml python-dotenv

# 8. 创建必要目录
echo "📁 [8/10] 创建数据目录..."
mkdir -p data logs

# 9. 生成配置文件
echo "⚙️ [9/10] 生成配置文件..."

cat > .env << EOF
# InfluxDB 配置
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=$INFLUX_TOKEN
INFLUX_ORG=ceramic-workshop
INFLUX_BUCKET=waterpump

# PLC 配置
USE_REAL_PLC=true
PLC_IP=192.168.1.10
PLC_RACK=0
PLC_SLOT=1

# 轮询配置
ENABLE_POLLING=true
POLLING_INTERVAL=5
BATCH_SIZE=30

# 本地缓存
LOCAL_CACHE_PATH=data/cache.db
CACHE_RETRY_INTERVAL=60
CACHE_MAX_RETRY=5

# API 配置
API_PORT=8081
LOG_LEVEL=INFO
EOF

echo "✅ 配置文件已生成: .env"
echo "⚠️ 请根据实际情况修改 PLC_IP"
echo "📝 InfluxDB Token: $INFLUX_TOKEN"

# 10. 配置开机自启
echo "🔄 [10/10] 配置开机自启..."

mkdir -p ~/.termux/boot

# InfluxDB 启动脚本
cat > ~/.termux/boot/01_start_influxdb.sh << 'INFLUXBOOT'
#!/data/data/com.termux/files/usr/bin/bash
cd ~/influxdb
./influxd \
    --bolt-path=./data/influxd.bolt \
    --engine-path=./data/engine \
    --http-bind-address=:8086 \
    > logs/influxdb_$(date +%Y%m%d).log 2>&1 &
echo $! > data/influxdb.pid
echo "[$(date)] InfluxDB 已启动 (PID: $!)" >> logs/startup.log
INFLUXBOOT

chmod +x ~/.termux/boot/01_start_influxdb.sh

# 后端启动脚本
cat > ~/.termux/boot/02_start_waterpump.sh << 'BACKENDBOOT'
#!/data/data/com.termux/files/usr/bin/bash

# 等待 InfluxDB 启动
sleep 15

cd ~/waterpump-backend
python main.py > logs/boot_$(date +%Y%m%d).log 2>&1 &
echo $! > data/backend.pid
echo "[$(date)] 后端服务已启动 (PID: $!)" >> logs/startup.log
BACKENDBOOT

chmod +x ~/.termux/boot/02_start_waterpump.sh

# 创建手动启动脚本
cat > ~/waterpump-backend/start.sh << 'STARTSCRIPT'
#!/data/data/com.termux/files/usr/bin/bash
# 手动启动后端服务

cd ~/waterpump-backend

# 检查是否已运行
if [ -f data/backend.pid ]; then
    PID=$(cat data/backend.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "⚠️ 服务已在运行 (PID: $PID)"
        echo "如需重启，请先执行: ./stop.sh"
        exit 1
    fi
fi

# 启动服务
echo "🚀 正在启动后端服务..."
python main.py > logs/manual_$(date +%Y%m%d_%H%M%S).log 2>&1 &

# 记录 PID
echo $! > data/backend.pid
echo "✅ 服务已启动 (PID: $!)"
echo "📋 查看日志: tail -f logs/manual_*.log"
echo "🛑 停止服务: ./stop.sh"
STARTSCRIPT

chmod +x ~/waterpump-backend/start.sh

# 创建停止脚本
cat > ~/waterpump-backend/stop.sh << 'STOPSCRIPT'
#!/data/data/com.termux/files/usr/bin/bash
# 停止后端服务

cd ~/waterpump-backend

if [ ! -f data/backend.pid ]; then
    echo "⚠️ PID 文件不存在，可能服务未运行"
    exit 1
fi

PID=$(cat data/backend.pid)

if ps -p $PID > /dev/null 2>&1; then
    echo "🛑 正在停止服务 (PID: $PID)..."
    kill $PID
    sleep 2
    
    if ps -p $PID > /dev/null 2>&1; then
        echo "⚠️ 正常停止失败，强制终止..."
        kill -9 $PID
    fi
    
    echo "✅ 服务已停止"
else
    echo "⚠️ 进程不存在 (PID: $PID)"
fi

rm -f data/backend.pid
STOPSCRIPT

chmod +x ~/waterpump-backend/stop.sh

# 创建状态检查脚本
cat > ~/waterpump-backend/status.sh << 'STATUSSCRIPT'
#!/data/data/com.termux/files/usr/bin/bash
# 检查后端服务状态

cd ~/waterpump-backend

echo "======================================================================"
echo "📊 后端服务状态"
echo "======================================================================"

# 检查进程
if [ -f data/backend.pid ]; then
    PID=$(cat data/backend.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "✅ 服务正在运行 (PID: $PID)"
        
        # 检查端口
        if netstat -tuln 2>/dev/null | grep -q ":8081"; then
            echo "✅ 端口 8081 已监听"
        else
            echo "⚠️ 端口 8081 未监听"
        fi
        
        # 检查 API
        if curl -s http://localhost:8081/health > /dev/null 2>&1; then
            echo "✅ API 健康检查通过"
        else
            echo "❌ API 健康检查失败"
        fi
    else
        echo "❌ 服务未运行 (PID 文件存在但进程不存在)"
    fi
else
    echo "❌ 服务未运行 (无 PID 文件)"
fi

echo ""
echo "📁 数据库文件:"
ls -lh data/*.db 2>/dev/null || echo "  (无数据库文件)"

echo ""
echo "📋 最新日志 (最后 10 行):"
tail -10 logs/*.log 2>/dev/null || echo "  (无日志文件)"

echo "======================================================================"
STATUSSCRIPT

chmod +x ~/waterpump-backend/status.sh

# 完成提示
echo ""
echo "======================================================================"
echo "✅ 部署完成！"
echo "======================================================================"
echo ""
echo "📝 下一步操作:"
echo ""
echo "1️⃣ 启动 InfluxDB:"
echo "   cd ~/influxdb"
echo "   bash ~/.termux/boot/01_start_influxdb.sh"
echo ""
echo "2️⃣ 验证 InfluxDB:"
echo "   curl http://localhost:8086/health"
echo ""
echo "3️⃣ 修改后端配置 (如需要):"
echo "   nano ~/waterpump-backend/.env"
echo "   (修改 PLC_IP 为实际 IP 地址)"
echo ""
echo "4️⃣ 启动后端:"
echo "   cd ~/waterpump-backend"
echo "   ./start.sh"
echo ""
echo "5️⃣ 检查服务状态:"
echo "   ./status.sh"
echo ""
echo "6️⃣ 查看日志:"
echo "   tail -f logs/manual_*.log"
echo ""
echo "7️⃣ 停止服务:"
echo "   ./stop.sh"
echo ""
echo "8️⃣ 开机自启:"
echo "   需要安装 Termux:Boot"
echo "   https://f-droid.org/packages/com.termux.boot/"
echo ""
echo "9️⃣ 安装 Flutter App:"
echo "   将 app-release.apk 传输到 /sdcard/"
echo "   执行: pm install -r /sdcard/app-release.apk"
echo ""
echo "🔑 InfluxDB 凭据:"
echo "   URL: http://localhost:8086"
echo "   Username: admin"
echo "   Password: influxdb123456"
echo "   Token: $INFLUX_TOKEN"
echo "   (Token 已保存到 ~/influxdb/config/token.txt)"
echo ""
echo "======================================================================"

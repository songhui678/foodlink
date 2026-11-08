# 食链通 FoodLink V1.0

面向中国中小型食品生产企业、食品经销商和食品贸易公司的本地 Excel 数据管理工具。

食链通不是 ERP，也不替代企业现有进销存软件。它专注于解决日常 Excel 管理中的重复录入、客户/商品匹配困难、订单与发货核对效率低、销售统计和报表导出繁琐等问题。

> 让食品企业的 Excel 数据自动关联、核对和分析。

## 一、项目介绍

- 界面语言：简体中文。
- 部署方式：本地部署，数据保存在用户自己的电脑或服务器上的 MongoDB 中。
- 第一版定位：本地单用户、单企业模式，数据库结构预留 `tenant_id`，便于未来扩展多企业隔离。
- 不接入付费 API，不依赖互联网，不把企业数据上传到第三方云端。

## 二、功能说明

系统包含 13 个页面：

1. **系统首页**：客户总数、商品总数、订单总数、本月销售额、本月订单数量、待处理匹配异常、待处理订单异常、最近导入记录。
2. **数据导入**：多文件、多 Sheet、CSV/Excel 读取，前 20 行预览，自动识别字段，手动字段映射，必填/空值/日期/金额/数量校验，重复文件提示，导入批次记录。
3. **客户管理**：客户列表、搜索、区域筛选、新增、编辑、软删除、恢复、重复客户检查、Excel 导出。
4. **客户匹配**：客户编码 > 手机号 > 标准化名称 > 模糊候选建议；支持多候选人工选择，不会自动确认模糊结果。
5. **商品管理**：商品列表、搜索、分类筛选、新增、编辑、软删除、规格重复检查、Excel 导出。
6. **商品匹配**：商品编码 > 名称+规格 > 标准化名称候选 > 模糊建议；同名不同规格不会被自动合并。
7. **订单管理**：按订单编号、客户、商品、日期查询，订单明细，重复订单检测，金额异常检测，导出。
8. **订单核对**：按订单编号和商品编码汇总发货数量，支持一个订单多次发货，识别全部发货、部分发货、超量发货、未发货、订单不存在、商品/客户不匹配、数据异常。
9. **发货管理**：发货记录查询、手工补录、重复发货单检查、导出。
10. **销售分析**：月度销售额/订单数趋势、客户/商品/区域排行、客户/商品明细、销售增长、销售异常，Plotly 图表。
11. **报表导出**：11 类中文 Excel 报表，带表头样式、自动列宽、金额/日期格式和文本编码格式。
12. **导入历史**：批次号、文件名、Sheet、总行数、成功/失败行数、状态、错误报告、导入日志。
13. **系统设置**：MongoDB 连接检测、数据库初始化与索引、业务设置、备份/恢复、演示数据生成与清理、临时文件清理。

### 字段类型

- 客户：客户编码、客户名称、联系人、手机号、所属区域、详细地址。
- 商品：商品编码、商品名称、商品规格、商品单位、商品分类、商品价格。
- 订单：订单编号、客户编码、客户名称、商品编码、商品名称、商品规格、订单日期、订单数量、单价、金额。
- 发货：发货单号、订单编号、客户编码、商品编码、发货日期、发货数量。
- 回款：回款单号、客户编码、回款日期、回款金额、备注。

### 关键业务规则

- 手机号、客户编码、商品编码、订单编号统一按字符串保存，不会变成科学计数法，不会丢失前导零。
- 金额使用 `Decimal` 计算，写入 MongoDB 使用 `Decimal128`，禁止用浮点数直接累加金额。
- 模糊匹配只提供候选建议，必须人工确认。
- 同名商品但规格不同视为不同商品，不会自动合并。
- 重复订单编号不会静默覆盖，默认跳过并记录提示。
- 一个订单可以对应多张发货单；核对时先按订单编号+商品编码汇总发货数量，再与订单数量比较。
- 所有删除操作为软删除或需要二次确认。
- 页面异常只显示中文友好提示，详细堆栈写入 `logs/foodlink.log`，日志中的手机号和 MongoDB 密码会脱敏。

## 三、技术架构

| 层 | 技术 |
|---|---|
| 前端 | Streamlit |
| 数据库 | MongoDB |
| 数据访问 | PyMongo |
| Excel/CSV | Pandas、OpenPyXL、xlrd |
| 金额精度 | Python Decimal / BSON Decimal128 |
| 模糊匹配 | RapidFuzz（未安装时自动降级为 difflib） |
| 图表 | Plotly |
| 配置/校验 | Pydantic、python-dotenv、PyYAML |
| 测试 | Pytest / unittest（测试文件兼容 Pytest 自动发现） |

项目采用模块化分层：

- `pages/`：只负责界面与交互。
- `services/`：业务逻辑、匹配、核对、分析、导出、备份。
- `database/`：连接、索引、仓储层。
- `models/`：Pydantic 数据模型。
- `utils/`：Decimal、手机号、Excel、校验、日志、UI 工具。

## 四、环境要求

- Python 3.10–3.12（推荐 Python 3.12）。
- MongoDB 6.0+（推荐 7.0）。
- 操作系统：Windows 10/11、macOS、Linux。
- 浏览器：Chrome、Edge、Firefox 近期版本。

## 五、Python 安装说明

### Windows

1. 从 <https://www.python.org/downloads/> 下载 Python 3.12。
2. 安装时勾选 **Add Python to PATH**。
3. 打开 PowerShell，执行：

```powershell
python --version
pip --version
```

### macOS

```bash
brew install python@3.12
python3.12 --version
```

### Linux

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
python3 --version
```

## 六、MongoDB 安装说明

### macOS（Homebrew）

```bash
brew tap mongodb/brew
brew install mongodb-community@7.0
brew services start mongodb-community@7.0
```

检查：

```bash
mongosh --quiet --eval "db.runCommand({ping:1})"
```

### Windows

1. 从 MongoDB 官网下载 MongoDB Community Server 7.0 MSI。
2. 安装时选择 **Install MongoDB as a Service**。
3. 默认连接地址：`mongodb://localhost:27017/`。

### Linux（Ubuntu）

按 MongoDB 官方文档添加软件源后执行：

```bash
sudo systemctl start mongod
sudo systemctl enable mongod
```

### Docker（仅启动 MongoDB）

```bash
docker compose up -d mongodb
```

本项目不要求应用本身运行在 Docker 中。

## 七、MongoDB 数据库创建说明

MongoDB 会在首次写入时自动创建数据库和集合。数据库默认名称为 `foodlink`，无需手工执行 `CREATE DATABASE`。

项目使用以下集合：

1. `customers`
2. `products`
3. `sales_orders`
4. `sales_order_items`
5. `delivery_records`
6. `payment_records`
7. `import_batches`
8. `import_logs`
9. `matching_logs`
10. `error_logs`
11. `field_mapping_configs`
12. `system_settings`

运行初始化脚本会自动创建索引和默认设置。

## 八、环境变量配置

复制示例文件：

```bash
cp .env.example .env
```

`.env` 示例：

```dotenv
MONGODB_URI=mongodb://localhost:27017/
MONGODB_DATABASE=foodlink
MONGODB_TEST_DATABASE=foodlink_test
MAX_FILE_SIZE_MB=50
PAGE_SIZE=20
TENANT_ID=default
LOG_LEVEL=INFO
```

- `MONGODB_URI`：MongoDB 连接串。若启用用户名密码，请使用环境变量保存，禁止硬编码到代码中。
- `MONGODB_DATABASE`：正式业务数据库，默认 `foodlink`。
- `MONGODB_TEST_DATABASE`：测试数据库，名称必须包含 `test`，测试不会写入正式库。
- `MAX_FILE_SIZE_MB`：单文件大小限制，默认 50MB。

## 九、依赖安装命令

```bash
cd foodlink
python3 -m venv .venv
source .venv/bin/activate        # Windows 使用 .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 十、初始化数据库命令

```bash
python scripts/init_database.py
```

初始化内容：

- 检测 MongoDB 连接；
- 创建客户、商品、订单、发货、回款、批次、日志、映射配置、系统设置索引；
- 写入默认企业名称、文件大小限制等设置；
- 打印各集合文档数。

## 十一、启动命令

方式一（推荐）：

```bash
./run.sh          # Linux / macOS
run.bat           # Windows
```

方式二：

```bash
streamlit run 首页.py
```

默认访问地址：<http://localhost:8501>

MongoDB 默认地址：`mongodb://localhost:27017/`

如果 MongoDB 未启动，应用仍可启动，但页面会显示清晰的中文连接提示，不会直接显示 Python 堆栈。

## 十二、测试命令

```bash
pytest -q
```

如果当前环境没有安装 Pytest，也可以直接运行：

```bash
python -m unittest discover -s tests -v
```

测试覆盖：

1. Excel 正常读取。
2. Excel 多 Sheet 读取。
3. Excel 字段映射。
4. 手机号前导零保留。
5. 客户编码前导零保留。
6. 重复手机号多候选匹配。
7. 客户名称模糊匹配建议。
8. 商品规格不同不自动合并。
9. 重复订单识别。
10. 订单金额精度。
11. 一个订单多次发货。
12. 订单数量与发货数量差异。
13. 空数据处理。
14. 错误数据导出。
15. MongoDB 连接失败处理。
16. 端到端流程与数据库备份/恢复。

测试使用独立测试数据库 `foodlink_test`；如果运行环境无法访问 localhost（例如受限沙箱），测试会自动切换到进程内 MongoDB mock，绝不会破坏正式 `foodlink` 数据库。

## 十三、数据备份方法

### 页面备份

进入 **系统设置 → 备份与恢复 → 立即备份数据库**。备份文件保存在 `backups/`，格式为 zip 内包含 BSON JSON 集合文件，可下载。

### 命令行备份

```bash
python scripts/backup_database.py
python scripts/backup_database.py --output backups/
```

### mongodump 方式（可选）

如果已安装 MongoDB Database Tools：

```bash
mkdir -p backups/mongodump_$(date +%Y%m%d)
mongodump --uri="mongodb://localhost:27017/" --db=foodlink --out=backups/mongodump_$(date +%Y%m%d)
```

## 十四、数据恢复方法

### 页面恢复

进入 **系统设置 → 备份与恢复**：

1. 上传 `foodlink_backup_*.zip`。
2. 选择“合并（保留现有数据）”或“覆盖（先清空业务集合）”。
3. 覆盖恢复必须输入“确认覆盖”，并再次勾选确认。
4. 点击“执行恢复”。

建议恢复前先创建一次当前数据库备份。

### mongorestore 方式（可选）

```bash
mongorestore --uri="mongodb://localhost:27017/" --db=foodlink backups/mongodump_20260101/foodlink
```

## 十五、常见问题处理

### 1. 页面提示“无法连接 MongoDB 数据库”

- 确认 MongoDB 服务已启动：
  - macOS：`brew services start mongodb-community@7.0`
  - Windows：服务管理器启动 `MongoDB` 服务
  - Linux：`sudo systemctl start mongod`
- 检查 `.env` 中的 `MONGODB_URI`。
- 检查端口 27017 是否被占用或防火墙拦截。

### 2. 上传 Excel 后手机号前导零丢失

Excel 中如果手机号已存为“数值”格式，前导零在 Excel 内部已经丢失。请把手机号列设置为“文本”后重新填写/导出。系统对文本单元格会完整保留，不会主动转成科学计数法。

### 3. 字段没有自动识别

不同企业列名不同，请在“字段映射”中手动选择对应列。保存映射方案后，下次可以在“已保存的映射方案”中直接应用。

### 4. 为什么模糊匹配没有自动确认？

为避免把不同客户或不同规格商品错误合并，系统只提供候选建议。请在“客户匹配/商品匹配”页人工选择。

### 5. 为什么同名商品没有合并？

商品名称相同但规格不同必须视为不同商品。系统不会自动合并，请核对规格后手工确认。

### 6. 订单重复导入会怎样？

系统会检测文件哈希和订单编号。重复文件会提示“跳过/重新导入/取消”；重复订单编号默认跳过，不会覆盖已有数据。

### 7. 报表中的编码/手机号变成科学计数法

导出时这些列会强制写成文本格式 `@`。如果仍显示异常，请检查原始 Excel 是否已经把值存成数值。

### 8. 测试数据库会污染正式数据吗？

不会。测试只使用 `foodlink_test`，测试结束自动删除；受限环境会使用进程内 mock。

### 9. 端口 8501 被占用

```bash
streamlit run 首页.py --server.port 8502
```

### 10. 如何查看详细错误

查看 `logs/foodlink.log`。页面只显示友好中文提示，日志会脱敏手机号和数据库密码。

## 十六、项目目录结构

```text
foodlink/
├── 首页.py
├── requirements.txt
├── .env.example
├── .gitignore
├── config.yaml
├── docker-compose.yml
├── run.sh
├── run.bat
├── pytest.ini
├── README.md
├── pages/
│   ├── 01_数据导入.py
│   ├── 02_客户管理.py
│   ├── 03_客户匹配.py
│   ├── 04_商品管理.py
│   ├── 05_商品匹配.py
│   ├── 06_订单管理.py
│   ├── 07_订单核对.py
│   ├── 08_发货管理.py
│   ├── 09_销售分析.py
│   ├── 10_报表导出.py
│   ├── 11_导入历史.py
│   └── 12_系统设置.py
├── services/
│   ├── excel_service.py
│   ├── import_service.py
│   ├── customer_service.py
│   ├── product_service.py
│   ├── matching_service.py
│   ├── order_service.py
│   ├── delivery_service.py
│   ├── analysis_service.py
│   ├── report_service.py
│   ├── backup_service.py
│   └── settings_service.py
├── database/
│   ├── connection.py
│   ├── indexes.py
│   └── repositories/
├── models/
├── utils/
├── tests/
├── scripts/
│   ├── init_database.py
│   ├── generate_demo_data.py
│   └── backup_database.py
├── uploads/
├── exports/
├── backups/
└── logs/
```

## 十七、演示数据

方式一：进入 **系统设置 → 演示数据 → 生成演示数据**。

方式二：

```bash
python scripts/generate_demo_data.py
```

演示数据全部带以下标识：

- 客户编码、商品编码以 `TEST-` 开头；
- 名称前缀为 `【测试数据】`；
- 数据库文档带 `is_demo=True`；
- 可一键清除，不影响正式数据。

演示流程覆盖：客户、商品、订单多明细、一个订单多次发货、部分发货、超量发货、未发货、订单不存在、未匹配客户、销售分析和 Excel 报表。

## 十八、第一次使用自己的 Excel 数据

建议按以下顺序操作：

1. 到 **系统设置 → 数据库连接**，确认 MongoDB 正常，点击“初始化数据库与索引”。
2. 到 **数据导入**，先选择“客户资料”类型，上传客户 Excel，预览前 20 行，手动映射字段，点击“检查此文件”。
3. 查看错误行；如无错误，勾选确认后点击“确认导入此文件”。
4. 用同样方式导入“商品资料”。
5. 导入“销售订单”；检查“客户匹配/商品匹配”页面是否有待处理记录，人工确认。
6. 导入“发货记录”；到“订单核对”查看全部/部分/超量/未发货差异。
7. 到“销售分析”选择日期范围查看图表和排行榜。
8. 到“报表导出”下载需要的 Excel 报表。
9. 首次操作前建议在“系统设置 → 备份与恢复”创建一次空库备份，熟悉恢复流程。

## 十九、V1.0 已知限制

- 第一版是本地单用户应用，没有登录、角色权限和多租户隔离；数据库结构已预留 `tenant_id`。
- 不接入大语言模型、不调用付费 API、不自动上传企业数据。
- 不替代 ERP 的库存、采购、生产、财务总账等功能。
- Excel 中已经是数值格式的手机号/编码，前导零在源文件阶段可能已丢失，系统无法恢复被 Excel 丢弃的信息。
- 模糊匹配默认使用 RapidFuzz；如果运行环境未安装 RapidFuzz，会自动降级为标准库 difflib，建议在生产环境安装 requirements 中的完整依赖。
- 订单重复处理采用“跳过并提示”的安全策略，第一版不提供自动覆盖或自动合并重复订单的按钮。
- 备份文件采用 BSON JSON 打包 zip，适合本机单机部署；超大数据量企业建议额外使用 mongodump 增量/全量备份方案。


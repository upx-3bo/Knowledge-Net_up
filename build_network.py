"""
从 data_2026.json 构建 2026 汽车创新技术知识网络（从下至上）
- Level 1: 顶层领域
- Level 2: 子领域
- Level 3: 具体技术点
- Level 0: 支撑材料（论文/专利/新闻/技术文件）
"""
import json, os, sys, sqlite3

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))
from services.knowledge_base import KnowledgeBase, DB_PATH

# ===== 1. 清空现有数据 =====
conn = sqlite3.connect(DB_PATH)
conn.execute("DELETE FROM vertices")
conn.execute("DELETE FROM edges")
conn.execute("DELETE FROM node_notes")
conn.execute("DELETE FROM sqlite_sequence WHERE name='edges'")
conn.commit()
conn.close()
print("已清空数据库")

kb = KnowledgeBase()

# ===== 2. 读取数据 =====
with open("data_2026.json", "r", encoding="utf-8") as f:
    entries = json.load(f)
print(f"读取 {len(entries)} 条 2026 年记录")

# ===== 3. 定义层级映射 =====
# 每条记录: (domain, subdomain, tech_point, material_type, remark_brief)
# material_type: paper / patent / news / doc
MAPPING = {
    "恩梯恩开发高精度轴承扭矩计算方法": ("轻量化材料", "轴承技术", "轴承扭矩计算", "news", "恩梯恩轴承扭矩"),
    "斯坦福大学用银涂层增强电解质抗裂性": ("动力电池", "固态电池", "银涂层抗裂电解质", "paper", "斯坦福银涂层"),
    "直驱传动灵巧手+通用机器人": ("机器人与具身智能", "灵巧手", "直驱灵巧手", "news", "SharpaWave灵巧"),
    "日本科研人员发明新型固态氢载体": ("动力电池", "氢能", "光释氢固态载体", "paper", "层状氢硅烷L-HSi"),
    "现代智能汽车中的无线技术36——V2X（8）": ("感知与自动驾驶", "V2X", "V2X边缘计算", "doc", "V2X RSU+MEC"),
    "圣莱特申请用于3D打印轻量化结构的光固化复合材料专利": ("制造工艺", "3D打印", "光固化3D打印", "patent", "圣莱特光固化专利"),
    "安道拓推出突破性座椅设计解决方案ModuTec": ("智能座舱", "座椅系统", "模块化座椅", "news", "ModuTec座椅"),
    "Micro LED微显再获突破": ("智能座舱", "车载显示", "MicroLED背板", "news", "Sapien Micro"),
    "宝马新专利：车载触摸屏增设“触摸感应条”": ("智能座舱", "人机交互", "触摸感应条", "patent", "宝马触摸感应条"),
    "Microchip扩展maXTouch® M1触摸屏控制器系列": ("智能座舱", "车载显示", "智能互容触控", "news", "maXTouch M1"),
    "科思创汽车内饰新突破：给门板加“光影”": ("车身与涂层", "内饰涂层", "智能表面涂层", "news", "科思创INSQIN"),
    "旭化成开发出不含PFAS的PA66": ("轻量化材料", "工程塑料", "无PFAS聚酰胺", "news", "旭化成无PFAS PA6"),
    "一款环视车载镜头（2G4P）FOV210°-(OD32)": ("感知与自动驾驶", "车载镜头", "超广角环视镜头", "doc", "2G4P环视镜头"),
    "效率提升十倍以上！上海交大与小米发布AI轻合金智能研发技术平台": ("制造工艺", "AI研发", "AI轻合金平台", "news", "交大小米AI轻合金"),
    "休斯顿大学开发“热二极管”改善散热": ("热管理", "散热技术", "热二极管", "paper", "休斯顿热二极管"),
    "超材料研究助力设计更优质的植入物、机器人手和汽车保险杠": ("轻量化材料", "超材料", "超材料晶胞设计", "paper", "超材料晶胞研究"),
    "澳大利亚科学家探索从透锂长石中提取锂的工艺": ("动力电池", "电池材料", "透锂长石提锂", "news", "LithSonic提锂"),
    "达尼森推出DN1000ID电流传感器系列新产品": ("电驱与功率电子", "传感器", "磁通门电流传感器", "news", "DN1000ID传感器"),
    "英利汽车新获专利：革新碳纤维缠绕技术": ("轻量化材料", "碳纤维", "碳纤维缠绕夹持", "patent", "英利碳纤维缠绕"),
    "方向盘变触摸屏 通用汽车申请智能转向系统专利": ("智能座舱", "人机交互", "触摸屏方向盘", "patent", "通用触摸屏方向盘"),
    "艾迈斯欧司朗推出AS5173磁位置传感器": ("底盘与悬架", "传感器", "磁位置传感器", "news", "AS5173传感器"),
    "哥伦比亚大学开发出新型电解质": ("动力电池", "固态电池", "疏盐凝胶电解质", "paper", "哥大疏盐电解质"),
    "3D打印“几何电池”突破传统束缚": ("动力电池", "电池结构", "3D打印几何电池", "news", "几何电池3D打印"),
    "JBD“狮鹫Ⅰ”车规级MicroLED投影面板问世": ("智能座舱", "车载显示", "MicroLED投影", "news", "JBD狮鹫MicroLE"),
    "利用近红外光谱技术 Trinamix公司开发用于汽车的触控式酒精传感器": ("安全技术", "传感器", "酒精传感器", "news", "酒精传感器"),
    "3D打印实现2微米微流控通道": ("制造工艺", "3D打印", "微流控3D打印", "paper", "微流控3D打印"),
    "无序多孔触发性能跃升——高性能聚合物热电材料": ("热管理", "热电材料", "热电聚合物膜", "paper", "热电聚合物膜"),
    "瑞萨电子推出RH850/U2C汽车控制器": ("软件与E/E架构", "控制器", "28nm车规MCU", "news", "RH850/U2C MC"),
    "安全带70载创新不止！沃尔沃“多自适应”安全带登场": ("安全技术", "乘员保护", "自适应安全带", "news", "沃尔沃自适应安全带"),
    "Horse Powertrain全新高效非晶电机全球首发": ("电驱与功率电子", "电机", "非晶高效电机", "news", "Horse非晶电机"),
    "ORNL科学家将废旧汽车铝材转化为高性能金属": ("轻量化材料", "铝合金", "回收铝高性能化", "news", "ORNL RidgeAl"),
    "采埃孚和SiliconAuto联合推出用于ADAS计算的I/O芯片": ("感知与自动驾驶", "ADAS计算", "ADAS I/O芯片", "news", "采埃孚ADAS I/O"),
    "新思科技推出电子数字孪生平台": ("软件与E/E架构", "开发工具", "电子数字孪生", "news", "新思数字孪生"),
    "FIBRECOAT推出镀铝玄武岩纤维电动车汽车电池盒": ("轻量化材料", "复合材料", "镀铝玄武岩电池壳", "news", "FibreCoat电池壳"),
    "奇瑞发布犀牛电池技术": ("动力电池", "电池系统", "犀牛电池", "news", "奇瑞犀牛电池"),
    "美国阿肯色大学研发纳米涂层": ("动力电池", "电池材料", "硫化锆纳米涂层", "paper", "阿肯色硫化锆涂层"),
    "Magna：热管理而非电池容量": ("热管理", "电池热管理", "AI智能热管理", "doc", "Magna智能热管理"),
    "阿维塔发布太行智控2.0技术": ("底盘与悬架", "主动悬架", "电磁避震", "news", "阿维塔太行2.0"),
    "有研工研院申请轻质高强高韧高镁含量铝合金专利": ("轻量化材料", "铝合金", "高镁铝合金", "patent", "有研高镁铝合金"),
    "谷歌推出面向软件定义汽车（SDV）的 Android Automotive OS（AAOS SDV）": ("软件与E/E架构", "操作系统", "AAOS SDV", "news", "谷歌AAOS SDV"),
    "厚片吸塑工艺展开汽车结构件应用": ("制造工艺", "成型工艺", "厚片吸塑成型", "doc", "厚片吸塑结构件"),
    "马瑞利区域控制单元ZCU荣获年度工程产品奖": ("软件与E/E架构", "E/E架构", "区域控制单元", "news", "马瑞利ZCU"),
    "东北大学开发超声波焊接": ("动力电池", "固态电池", "超声波焊接界面", "paper", "东北大学超声波焊接"),
    "自修复涂层：光热响应SMP+石墨烯": ("车身与涂层", "涂层技术", "自修复涂层", "doc", "SMP石墨烯自修复"),
    "Canatu (芬兰)：透明碳纳米管 (CNT) 传感器加热膜": ("感知与自动驾驶", "传感器", "CNT传感器加热膜", "news", "Canatu CNT加热"),
    "同驭汽车申请一种HIL硬件在环系统专利": ("制造工艺", "测试验证", "HIL测试系统", "patent", "同驭HIL系统"),
    "翰昂系统为电动汽车提供高度集成的冷却系统": ("热管理", "座舱热管理", "集成冷却系统", "news", "翰昂集成冷却"),
    "科思创、Marquardt和E Ink合作将显示屏嵌入汽车内饰中": ("智能座舱", "人机交互", "电子纸内饰显示", "news", "电子纸内饰显示"),
    "首钢股份联合吉利汽车研究院与江西豪斯特攻关新型锌基热成形钢拼焊双门环": ("轻量化材料", "高强钢", "锌基热成形门环", "news", "首钢锌基门环"),
    "马瑞利在2026北京国际汽车展上展示面向软件定义汽车的下一代座舱创新技术": ("智能座舱", "车载显示", "柱到柱屏座舱", "news", "马瑞利柱到柱屏"),
    "经纬恒润分享AI在底盘领域的应用探索": ("底盘与悬架", "底盘控制", "AI底盘控制", "doc", "经纬恒润AI底盘"),
    "福耀&小鹏打造行业首款AI调光隐私玻璃": ("智能座舱", "智能玻璃", "AI调光玻璃", "news", "福耀AI调光玻璃"),
    "汉高推出高性能防指纹涂层": ("车身与涂层", "涂层技术", "防指纹涂层", "news", "汉高防指纹涂层"),
    "陶瓷涂层制造商 FEYNLAB推出具备可自动修复轻微划痕的车身涂层": ("车身与涂层", "涂层技术", "自修复陶瓷涂层", "news", "FEYNLAB陶瓷涂层"),
    "Luminary推出首个用于整车碰撞预测的物理AI模型SHIFT-Crash": ("制造工艺", "AI仿真", "AI碰撞预测", "news", "SHIFT-Crash "),
    "法雷奥（Valeo）发布“AI 预测式”浸没式电池冷却系统": ("热管理", "电池热管理", "浸没式电池冷却", "news", "法雷奥浸没冷却"),
    "宝马集团与萨格勒布大学：利用人工智能推进电池电芯生产": ("制造工艺", "AI制造", "AI电芯生产", "news", "宝马AI电芯生产"),
    "嘉瑞国际：以材料创新重新定义轻量化": ("轻量化材料", "镁合金", "阻燃镁合金", "news", "嘉瑞阻燃镁合金"),
    "时代新材申请轻量化复合材料控制臂专利": ("底盘与悬架", "底盘部件", "复合材料控制臂", "patent", "时代新材控制臂"),
    "罗姆开发第五代SiC MOSFET": ("电驱与功率电子", "功率器件", "五代SiC MOSFET", "news", "罗姆五代SiC"),
    "宝益科技开发热管理材料核心技术": ("热管理", "热管理材料", "电池加热膜", "doc", "宝益PI加热膜"),
    "东华大学王宏志团队全光谱自适应智能玻璃的突破性研究": ("智能座舱", "智能玻璃", "全光谱电致变色", "paper", "东华DarpE变色玻璃"),
    "宁德时代子公司时代智能研发磐石L4全冗余原生底盘技术": ("底盘与悬架", "线控底盘", "L4冗余底盘", "news", "时代智能L4底盘"),
    "Saflex™ Evoca™ EAS 增强隔音中间膜": ("智能座舱", "智能玻璃", "隔音PVB中间膜", "news", "Saflex隔音膜"),
    "AGY与SAERTEX宣布开发先进的S-2 Glass®无捻织物": ("轻量化材料", "复合材料", "S-2玻璃NCF织物", "news", "S-2 Glass NC"),
    "ZFW研发并联合C-Therm推出新型高温防护式热流计": ("制造工艺", "测试设备", "高温热流计", "news", "ZFW高温热流计"),
    "Carbon ThreeSixty推出TFP技术热塑性复合材料空气动力学轮罩": ("轻量化材料", "复合材料", "TFP复合材料轮罩", "news", "Carbon Three"),
    "Chabot Mobility联合AI公司Dmillion": ("软件与E/E架构", "AI应用", "AI维修诊断", "news", "Chabot AI维修"),
    "AURORADE™研发企业自主研发最先进的金属薄膜涂层技术": ("车身与涂层", "涂层技术", "金属薄膜涂层", "news", "AURORADE极光表皮"),
    "奥地利AI CAE创业公司 Emmi AI 研发了通用CFD": ("制造工艺", "AI仿真", "免网格AI CFD", "news", "Emmi AI CFD"),
    "望友科技坚持全链路自研": ("制造工艺", "工业软件", "3D PCBA DFM", "news", "望友3D DFM V8"),
    "Envalior 安万特推出针对电动出行与智能电子的系列先进工程聚合物": ("轻量化材料", "工程塑料", "800V工程聚合物", "news", "安万特工程聚合物"),
    "西班牙IMDEA Materials等联合研究团队开发基于AlCl₄⁻气相插层的可扩展CNT纤维制造工艺": ("轻量化材料", "碳纤维", "气相插层CNT纤维", "paper", "IMDEA CNT纤维"),
    "LG新能源、3M等头部电池与特种材料供应商开发并集成了多层陶瓷": ("安全技术", "电池安全", "多层陶瓷热障", "news", "LG多层陶瓷热障"),
    "巴斯夫（联合现代设计中国）为现代IONIQ": ("智能座舱", "座椅系统", "TPU充气座椅", "news", "巴斯夫TPU Air H"),
    "Future Market Insights 发布全球汽车制动消音垫市场报告": ("底盘与悬架", "制动系统", "IoT制动消音垫", "news", "IoT制动消音垫"),
    "圣龙股份自主研发并规模化量产国内首款800V全主动液压悬架高压泵头": ("底盘与悬架", "主动悬架", "800V液压悬架泵", "news", "圣龙800V液压泵"),
    "Freudenberg Sealing Technologies在DIAvent®系列中推出DIAvent® maxFlow": ("安全技术", "电池安全", "可逆脱气阀", "news", "DIAvent maxF"),
    "Anna Bonanomi构建了电动汽车动力总成多物理场": ("电驱与功率电子", "电机", "多物理场NVH仿真", "paper", "多物理场NVH仿真"),
    "弗劳恩霍夫三家研究所与莱布尼茨复合材料研究所": ("制造工艺", "复合材料制造", "激光复材连接", "doc", "弗劳恩霍夫激光复材"),
    "古能（Gunnebo）旗下Minimax推出基于F-500 EA®": ("安全技术", "电池安全", "锂电池灭火方案", "news", "F-500 EA灭火"),
    "东南大学郝梦龙团队受传统榫卯启发": ("电驱与功率电子", "连接器", "机械超界面连接", "paper", "东南大学机械超界面"),
    "宁德时代获“纵梁总成及汽车底盘”发明专利授权": ("底盘与悬架", "底盘结构", "一体成型纵梁", "patent", "宁德一体纵梁"),
    "AGC推出涵盖HUD反射刀片": ("智能座舱", "智能玻璃", "多功能车载玻璃", "news", "AGC FeelInGl"),
    "博士研究员Sachin Kochrekar开发基于卟啉的薄聚合物膜": ("智能座舱", "智能玻璃", "卟啉变色电容器", "paper", "卟啉变色电容器"),
    "圣邦微电子推出车规级电子保险丝控制器SGM42148Q": ("电驱与功率电子", "配电", "电子保险丝", "news", "SGM42148Q电子保"),
    "美利信推出全球首款2线制2位霍尔开关MLX92344": ("电驱与功率电子", "传感器", "2线霍尔开关", "news", "MLX92344霍尔开关"),
    "陶氏公司推出DOW™ Cooling Science热管理材料科学平台": ("热管理", "热管理材料", "有机硅热管理", "news", "DOW有机硅热管理"),
    "GaN走向高电压减薄p-GaN定义穿通栅极": ("电驱与功率电子", "功率器件", "穿通栅极GaN", "news", "穿通栅极GaN HEMT"),
    "中电科55所、富加镓业": ("软件与E/E架构", "通信", "氮化镓射频+氧化镓", "news", "氮化镓射频+氧化镓"),
    "GM（通用汽车）实施“车网互动（V2G）全矩阵标配”": ("动力电池", "储能", "V2G+钠离子储能", "news", "通用V2G+钠离子"),
    "Ottawa Infotainment（Oi）推出Tucker Safety Package": ("安全技术", "主动安全", "集成安全套件", "news", "Tucker Safet"),
    "德国亚琛应用技术大学研究团队研发独立式微波等离子体技术": ("制造工艺", "碳纤维制造", "微波等离子预氧化", "paper", "亚琛微波等离子"),
    "日本九州大学Tao Bai团队提出基于双麦克风": ("智能座舱", "NVH", "前馈主动降噪", "paper", "九州大学主动降噪"),
    "首尔大学高承焕教授团队联合MIT及现代起亚": ("热管理", "座舱热管理", "透明辐射冷却膜", "paper", "首尔大学辐射冷却膜"),
    "北京交通大学与欣旺达的研究团队提出了一种基于图引导": ("动力电池", "电池管理", "图网络故障检测", "paper", "GraphSAGE故障检"),
    "Foundation Alloy 采用固态机械合金化工艺": ("轻量化材料", "超级金属", "固态合金化超级金属", "news", "Foundation超级"),
    "莱格特动力公司推出中端按摩系统（MCM）": ("智能座舱", "座椅系统", "气动按摩模块", "news", "莱格特气动按摩"),
    "合肥一通电子自主研发LNN本地节点网络系统": ("软件与E/E架构", "E/E架构", "LNN区域接入架构", "news", "合肥一通LNN架构"),
    "西安交通大学李苏植": ("轻量化材料", "耐高温合金", "ODS难熔合金", "paper", "西交大ODS难熔合金"),
    "立时集团（Nipsea Group）": ("车身与涂层", "涂层技术", "超黑涂层", "news", "立时超黑涂层"),
    "格拉茨技术大学联合布鲁塞尔自由大学": ("动力电池", "电池管理", "EIS车载BMS", "paper", "格拉茨EIS BMS"),
    "中研赢创自主研发“汽车悬架直线电机线圈背靠结构”": ("底盘与悬架", "主动悬架", "悬架直线电机", "patent", "中研赢创直线电机"),
    "上海交大与宁德时代联合研发一种用于锂电池极端热失控防护的双层异质陶瓷防隔热涂层": ("安全技术", "电池安全", "双层陶瓷防热涂层", "news", "交大宁德陶瓷涂层"),
    "太钢集团钢科公司": ("轻量化材料", "碳纤维", "T1100S碳纤维", "news", "太钢T1100S碳纤维"),
    "天马微电子发布全球首款3.16英寸圆形透明Micro LED显示屏": ("智能座舱", "车载显示", "圆形透明MicroLED", "news", "天马圆形MicroLED"),
    "西湖大学胡汪洋等研究团队构建并发布了覆盖2000年代初至2023年": ("软件与E/E架构", "AI应用", "EV政策数据库", "paper", "西湖大学EV政策库"),
    "浙大（浙江大学）研究团队受深海墨鱼骨": ("轻量化材料", "超材料", "墨鱼骨仿生多孔", "paper", "浙大墨鱼骨仿生"),
    "华东理工大学王健农教授团队提出“流体力学”新思路": ("轻量化材料", "碳纤维", "流体力学CNT纤维", "paper", "华理CNT纤维"),
    "Tecman 推出全面商业化的 ATP（抗热传播）垫片": ("安全技术", "电池安全", "ATP抗热传播垫片", "news", "Tecman ATP垫片"),
    "Melexis推出Triphibian®压力传感器系列的低压新变体": ("热管理", "传感器", "低压压力传感器", "news", "Melexis压力传感器"),
    "中国汽研联合吉利汽车研究院": ("动力电池", "电池管理", "热失控早期预警", "patent", "中国汽研热失控预警"),
    "英国工程与复合材料专业公司Dash-CAE": ("制造工艺", "3D打印", "LFAM碳纤维单体壳", "news", "Dash-CAE碳纤维壳"),
    "越疆联合西门子、奥普特等企业": ("机器人与具身智能", "工业机器人", "协作机器人电子皮肤", "news", "越疆SafeSkin机器"),
    "浩斯动力传动系统公司研发并发布了HORSE D20甲醇增程动力系统": ("电驱与功率电子", "动力总成", "甲醇增程轴向磁通", "news", "HORSE D20甲醇增"),
    "沅创智能发布了全球汽车工业领域首个“虚拟物理AI工程师”": ("制造工艺", "AI研发", "虚拟物理AI工程师", "news", "沅创愚公AI工程师"),
    "香港城市大学吕坚院士团队": ("轻量化材料", "铝合金", "3D打印耐热铝合金", "paper", "港城大耐热铝合金"),
    "南京工业大学、国网江苏省电力有限公司": ("热管理", "热管理材料", "石墨烯相变热膜", "patent", "石墨烯相变热膜"),
    "山东源航攻克了镁锂合金真空熔炼": ("轻量化材料", "镁合金", "镁锂合金量产", "news", "山东源航镁锂合金"),
    "中国科学技术大学程文龙教授团队研发出形状记忆复合相变材料": ("热管理", "散热技术", "形状记忆相变散热", "news", "中科大相变散热"),
    "中国一汽（红旗品牌）成功攻关高抗裂性自冲铆接": ("制造工艺", "连接工艺", "镁合金自冲铆接", "news", "红旗镁合金铆接"),
    "韩国科学技术院（KAIST）金英镇教授团队": ("动力电池", "电池制造", "太赫兹电极检测", "paper", "KAIST太赫兹检测"),
    "佛瑞亚海拉在中国实现新一代阳光雨量传感器规模化量产": ("感知与自动驾驶", "传感器", "5合1雨量传感器", "news", "佛瑞亚雨量传感器"),
    "汉威科技集团推出“空气质量传感器+水离子发生器”": ("智能座舱", "座舱环境", "空气净化联动", "news", "汉威空气净化联动"),
    "三菱化学推出两款全新碳纤维预浸料产品": ("轻量化材料", "碳纤维", "高韧性碳纤维预浸料", "news", "三菱化学碳纤维预浸料"),
    "中国科学院科研团队携手国内石化巨头联合研发并成功投产十万吨级稀土顺丁橡胶装置": ("轻量化材料", "橡胶材料", "稀土顺丁橡胶", "news", "中科院稀土顺丁橡胶"),
}

import re

def clean_title_fn(raw):
    "去掉标题前缀 '1、' '1、 ' 等，不误删 3D 中的 3"
    t = raw.strip()
    t = re.sub(r'^\d+[、\.\s]+', '', t)
    return t.strip()

def find_mapping(ct):
    "在 MAPPING 中查找匹配项"
    if ct in MAPPING:
        return MAPPING[ct]
    # 模糊：key 前 10 字符出现在标题中
    for key in MAPPING:
        if len(key) >= 10 and key[:10] in ct:
            return MAPPING[key]
        if len(ct) >= 10 and ct[:10] in key:
            return MAPPING[key]
    # 更宽松：用 key 的核心词匹配
    for key in MAPPING:
        # 取 key 中间 8 字符搜索
        mid = key[len(key)//4 : len(key)//4 + 8]
        if len(mid) >= 6 and mid in ct:
            return MAPPING[key]
    return None

vid_counter = 0
def make_vid(prefix):
    global vid_counter
    vid_counter += 1
    return f"{prefix}_{vid_counter:04d}"

domain_nodes = {}   # domain_name -> vid
subdomain_nodes = {}  # (domain, subdomain) -> vid
tech_nodes = {}     # tech_point -> vid
material_count = 0
edge_count = 0

# 创建领域节点 (level 1)
domains_seen = set()
for entry in entries:
    ct = clean_title_fn(entry["title"])
    m = find_mapping(ct)
    if not m:
        print(f"  [WARN] 未匹配: {ct[:50]}")
        continue
    
    domain, subdomain, tech_point, mat_type, mat_name = m
    if domain not in domains_seen:
        domains_seen.add(domain)
        vid = make_vid("domain")
        kb.insert_vertex("technology", vid, {"name": domain, "level": 1})
        domain_nodes[domain] = vid
        print(f"  创建领域 L1: {domain} ({vid})")

# 创建子领域节点 (level 2) 并连接到领域
for entry in entries:
    ct = clean_title_fn(entry["title"])
    m = find_mapping(ct)
    if not m:
        continue
    
    domain, subdomain, tech_point, mat_type, mat_name = m
    key = (domain, subdomain)
    if key not in subdomain_nodes:
        vid = make_vid("subdomain")
        kb.insert_vertex("technology", vid, {"name": subdomain, "level": 2})
        subdomain_nodes[key] = vid
        # 连接 子领域 → 领域 (belongs_to)
        kb.insert_edge("belongs_to", vid, domain_nodes[domain], {})
        edge_count += 1

# 创建技术点节点 (level 3) + 支撑材料节点 (level 0) 并连接
for entry in entries:
    ct = clean_title_fn(entry["title"])
    m = find_mapping(ct)
    if not m:
        continue
    
    domain, subdomain, tech_point, mat_type, mat_name = m
    
    # 技术点节点 (level 3)
    if tech_point not in tech_nodes:
        tvid = make_vid("tech")
        kb.insert_vertex("technology", tvid, {"name": tech_point, "level": 3})
        tech_nodes[tech_point] = tvid
        # 连接 技术点 → 子领域 (belongs_to)
        kb.insert_edge("belongs_to", tvid, subdomain_nodes[(domain, subdomain)], {})
        edge_count += 1
    else:
        tvid = tech_nodes[tech_point]
    
    # 支撑材料节点 (level 0) — 使用人工提炼的简称
    mvid = make_vid("mat")
    kb.insert_vertex("material", mvid, {
        "name": mat_name,
        "level": 0,
        "material_type": mat_type,
    })
    material_count += 1
    
    # 连接 技术点 → 支撑材料 (supports)
    kb.insert_edge("supports", mvid, tvid, {})  # 方向：支撑材料→技术点
    edge_count += 1
    
    # 添加备注（完整标题+内容）和链接
    remark = f"【{entry['date']}】{ct}\n\n{entry['content']}"
    kb.update_notes(mvid, remark, entry["link"])

# 统计
total_nodes = len(domain_nodes) + len(subdomain_nodes) + len(tech_nodes) + material_count
print(f"\n===== 构建完成 =====")
print(f"领域 (L1): {len(domain_nodes)}")
print(f"子领域 (L2): {len(subdomain_nodes)}")
print(f"技术点 (L3): {len(tech_nodes)}")
print(f"支撑材料 (L0): {material_count}")
print(f"总节点: {total_nodes}")
print(f"总边: {edge_count}")

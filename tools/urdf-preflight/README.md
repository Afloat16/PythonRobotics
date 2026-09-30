# URDF Preflight

**在启动仿真器之前，先检查机器人模型。**

[English](README.en.md) · [规则手册](docs/rules.md) · [调研与设计依据](docs/research.md) · [安全边界](SECURITY.md)

一个只读、零运行时依赖的 URDF 体检工具。把模型文件交给它，获得**问题位置、原因、下一步建议**，而不是等 ROS、仿真器或训练任务启动后再找模型错误。

适用于机械臂、移动机器人、夹爪和教学模型的 **URDF 文件工作流**。不要求安装 ROS、NumPy、图形界面或仿真器。不是硬件安全认证，也不是完整 URDF schema 验证器。

## 立即试用

需要 Python 3.10 或更新版本。在本项目目录中，**不安装也能运行**：

```bash
python -m urdf_preflight examples/healthy.urdf --profile simulation
python -m urdf_preflight examples/broken.urdf --format html -o report.html
```

第二条命令应返回退出码 `1`，因为示例故意包含错误。用浏览器打开 `report.html` 即可查看完整离线报告；不加载远程资源，不上传模型。

安装为普通命令：

```bash
python -m pip install .
urdf-preflight your_robot.urdf
urdf-preflight models/ --strict --format json -o preflight.json
```

项目尚未发布到 PyPI；不要使用 `pip install urdf-preflight` 猜测同名包。

本版本位于 `Afloat16/PythonRobotics` 的 `feat/urdf-preflight` 分支，独立目录为 `tools/urdf-preflight`，不依赖该仓库的其他代码：

```bash
git clone --depth 1 --single-branch --branch feat/urdf-preflight https://github.com/Afloat16/PythonRobotics.git
cd PythonRobotics/tools/urdf-preflight
python -m urdf_preflight examples/healthy.urdf
```

## 检查什么

| 类别 | 典型问题 |
|---|---|
| 模型结构 | 重名、缺少连杆、无效父子引用、多父节点、断开的根节点、闭环 |
| 关节与位姿 | 缺失/倒置限位、零轴、非单位轴、错误数字、四元数问题、mimic 引用/闭环 |
| 质量与惯性 | 不完整惯性块、非正质量、完整张量非正定、主惯量三角不等式、病态张量 |
| 几何与文件 | 非正尺寸、错误几何组合、丢失网格、包路径越界、未解析 URI |
| 版本与预处理 | URDF 1.0/1.1/1.2 差异、未展开的 Xacro、未验证的顶层扩展 |
| 仿真建议 | `simulation` 模式下，带几何的连杆缺少惯性或碰撞体 |

纯坐标系连杆允许没有惯性。仿真建议是 warning，不把所有可视化模型强行当作动力学模型。非正质量、零尺寸、负 mesh scale 等检查包含工程约束，严格程度可能高于某些解析器；规则手册明确区分。

## 网格与 ROS 包

普通相对路径基于 **URDF 所在目录**，不是当前终端目录。网格只检查文件存在性，不解析网格内容或计算体积。

```bash
urdf-preflight robot.urdf --package my_robot=/work/my_robot_description
```

`package://my_robot/meshes/base.stl` 将解析到 `/work/my_robot_description/meshes/base.stl`。映射必须指向包目录本身。不会调用 ROS 环境、下载远程文件或扫描整台计算机。没有映射时报告“未检查”，而不是假定文件缺失。

对只关心数值/结构的检查可以显式使用 `--no-mesh-check`，报告会记录此选项。

## 接入持续集成

```bash
urdf-preflight models/ --strict --format sarif -o results.sarif
```

支持 text、JSON、SARIF 2.1.0 和 HTML。`--strict` 把未抑制的 warning 也视为失败。SARIF 文件可交给兼容的代码扫描平台；本命令**不会上传**它。

| 退出码 | 含义 |
|---|---|
| `0` | 没有达到失败阈值的未抑制发现 |
| `1` | 检查发现错误，或 strict 模式下发现警告 |
| `2` | 文件读取、参数、基线或报告写入失败 |

已有模型库可以逐步接入：

```bash
urdf-preflight models/ --write-baseline baseline.json
# 首次依然按发现返回失败；审阅基线后再使用：
urdf-preflight models/ --baseline baseline.json --strict
```

基线不隐藏证据：JSON/HTML/SARIF 仍保留抑制的发现。指纹包含规则、路径、结构位置和错误内容，不包含行号；同一问题仅上下移动通常不触发新告警。**保持调用路径和工作目录一致**；改变错误值会形成新指纹。XML、读取失败、错误根节点、未知版本和未展开宏不能被基线/忽略规则静默放行。

`--ignore SIM001,SIM002` 可显式忽略规则。项目没有自动读取隐含配置文件，执行参数就是本次检查的主要配置。

## Python API

```python
from urdf_preflight import check_file

report = check_file("robot.urdf", profile="simulation")
for issue in report.issues:
    print(issue.code, issue.line, issue.message, issue.remedy)
```

`check_text(xml, path="robot.urdf", base_dir="models")` 适合编辑器或自定义流水线。返回类型定义在 `urdf_preflight/model.py`。API 返回报告，不抛出一般的文件读取/XML 错误；无效的 API 配置仍会抛出 `ValueError`。

## 维护和边界

```bash
python -m unittest discover -s tests -v
python -m urdf_preflight --list-rules
```

测试完全使用标准库；`scripts/verify_numerics.py` 是额外的 NumPy 开发期对照测试，不是运行时依赖。参见 [验证记录](docs/validation.md)。

本工具不展开 Xacro，不计算碰撞，不检查 mesh 拓扑/单位，不检查材质、传动和控制器的完整语义，也不保证某个仿真器正确导入合法模型。不应根据报告自动改写质量、惯性或运动限位。对不可信输入仍应使用受限工作目录、最新 Python 和操作系统资源限制。

独立建仓可使用 `python scripts/publish_standalone.py Afloat16/urdf-preflight` 预览，再加 `--execute` 发布。需要在本机预先登录 GitHub CLI；脚本仅复制本工具白名单文件到临时目录，不更改现有仓库，不覆盖同名远程仓库。参见脚本帮助。

## 开源与引用

本工具以 [MIT](LICENSE) 发布。实现、规则组织、测试样例和报告模板是本项目独立编写的内容，未复制参考项目的实现或机器人资产。URDF 格式、物理约束和报告标准的来源，以及同类工具的功能边界，完整记录在 [REFERENCES.md](REFERENCES.md) 和 [调研记录](docs/research.md)。不声称是首个 URDF 检查工具。

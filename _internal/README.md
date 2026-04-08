# DAS Processor V1.0 正式版 by C.W.Ng

## 1. 软件简介 (Introduction)
DAS Processor 是一款专为分布式光纤传感（DAS）数据设计的处理与分析软件。它集成了数据加载、交互式预处理、多维度可视化以及高级信号分析功能。软件采用模块化设计，支持节点式处理流程编辑，能够高效完成从原始数据到地质参数反演的全流程分析。

## 2. 启动方式 (Running)
确保已安装 Python 环境及相关依赖库（PyQt5, numpy, scipy, matplotlib, vmdpy）。
在终端运行：
```bash
python main.py
```

## 3. 功能详解 (Features)

### 3.1 数据加载 (Data Loading)
支持两种数据格式：
*   **Load Image**: 加载图片格式的数据（如 .png, .jpg），常用于查看已生成的瀑布图。
*   **Load TDMS**: 加载标准 TDMS 格式的原始 DAS 数据。
    *   *注意：加载图片后，建议在 Settings 中确认 dx (道间距) 和 dt (采样率) 参数，以保证坐标轴显示正确。*

### 3.2 预处理流程 (Pipeline Editor)
点击工具栏的 **Pipeline Editor** 打开节点编辑器。
*   **节点化操作**：通过拖拽连接不同处理节点（如 `Bandpass Filter`, `FK Filter`, `Normalize` 等）构建处理流。
*   **快捷操作**：
    *   **Undo/Redo**: 支持撤销/重做（Ctrl+Z / Ctrl+Y 或 Ctrl+Shift+Z），最大支持 10 步历史记录。
    *   **文件操作**: 支持 Ctrl+N (新建), Ctrl+S (保存), Ctrl+L (载入)。
    *   **全局小地图**: 右下角提供全局视图，支持按住左键拖拽平移，方便管理大型节点网络。
*   **实时生效**：编辑完成后，主界面会自动应用当前的 Pipeline 对原始数据进行重计算。

### 3.3 可视化视图 (Visualization)
主界面右侧面板提供多种视图模式，支持通过下拉菜单切换：
*   **Data Mode (数据模式)**:
    *   `Processed Data`: 默认模式，显示经过 Pipeline 处理后的时空数据。
    *   `Cross Correlation`: 显示互相关计算结果（需先运行 Standard Analysis -> Cross Correlation）。
    *   `VMD Mode`: 显示变分模态分解结果（需先运行 Standard Analysis -> VMD Analysis）。
*   **Analysis View (分析视图)**:
    *   `Standard View`: 标准分析组合视图，包含主图（瀑布图）、时频图、频谱图、FK谱。
    *   `Dispersion Analysis`: 频散能谱图（需先运行 Advanced Analysis -> Dispersion Analysis）。
    *   `Beamforming`: 波束形成能量图（需先运行 Advanced Analysis -> Beamforming）。
    *   `Velocity Analysis`: 速度反演结果图（需先运行 Advanced Analysis -> Velocity Analysis）。

### 3.4 交互操作 (Interaction)
*   **工具栏 (Toolbar)**:
    *   **Settings**: 位于最左侧，全局配置 dx, dt 等参数。
    *   **Load Data**: 下拉菜单，支持加载 Image 或 TDMS 数据。
    *   **Standard Analysis**: 下拉菜单，包含 `Cross Correlation` 和 `VMD Analysis`。
    *   **Advanced Analysis**: 下拉菜单，包含 `Dispersion Analysis`, `Beamforming`, `Velocity Analysis`。
    *   **Pipeline Editor**: 打开节点式预处理流程编辑器。
*   **播放回放**：在瀑布图上使用左键框选一个区域，会自动开始在该时间/空间范围内循环播放切片波形。
*   **视图切换**：点击不同的视图窗口（如 FK 谱、频谱图）可将其放大至主显示区。
*   **Help**: 点击工具栏 **Help** 按钮可直接查看本说明文档。

---

## 4. 高级分析操作指南 (Operation Guide)

### 4.1 频散分析 (Dispersion Analysis)
用于提取瑞利波/Scholte波的频散曲线。
1.  **启动**：点击工具栏 **Advanced Analysis -> Dispersion Analysis**。
2.  **设置**：配置频率范围 (Fmin, Fmax) 和相速度扫描范围 (Vmin, Vmax)。
3.  **计算**：点击 Compute，软件将生成频散能量谱。
4.  **交互查看**：在主界面的 `Dispersion Analysis` 视图中：
    *   **单击图像**：在以下 4 种显示模式间循环切换：
        1.  **Raw**: 原始能量谱。
        2.  **Raw + Curve**: 原始能量谱 + 自动提取的频散曲线（红线）。
        3.  **Smooth + Curve**: 平滑处理后的能量谱 + 频散曲线。
        4.  **Smooth**: 仅显示平滑后的能量谱。

### 4.2 速度反演 (Velocity Analysis)
基于 Scholte 波频散曲线反演水底沉积物的横波速度 ($V_s$) 结构。
1.  **前提**：必须先完成 **Dispersion Analysis** 并成功提取出频散曲线。
2.  **启动**：点击工具栏 **Advanced Analysis -> Velocity Analysis**。
3.  **配置模型参数**：
    *   **Water Properties**: 设置水体声速 ($V_p \approx 1500$ m/s)。
    *   **Sediment Search Bounds**: 设置沉积层 $V_s$ 范围（如 20-500 m/s）和厚度范围。
    *   **Substrate Bounds**: 设置基底 $V_s$ 范围。
4.  **运行反演**：点击 **Invert Profile**。程序将使用 L-BFGS-B 算法拟合观测频散曲线。
5.  **结果**：
    *   弹窗左侧显示观测值（黑点）与理论计算值（红线）的拟合情况。
    *   弹窗右侧显示反演得到的 $V_s$ 随深度变化的剖面。
    *   点击 **OK** 后，结果将显示在主界面的 `Velocity Analysis` 视图中。

### 4.3 波束形成 (Beamforming)
用于分析信号的来波方向和速度。
1.  **启动**：点击工具栏 **Advanced Analysis -> Beamforming**。
2.  **设置**：指定扫描角度范围、频率范围及介质声速。
3.  **查看**：结果将显示在 `Beamforming` 视图中，展示不同时间段的能量分布。图像已启用双线性插值平滑，视觉效果更佳。

### 4.4 互相关分析 (Cross Correlation)
用于计算参考道与其他所有道的互相关，常用于被动源干涉成像。
1.  **启动**：点击工具栏 **Standard Analysis -> Cross Correlation**。
2.  **设置**：选择参考道索引 (Ref Channel) 和最大时延 (Max Lag)。
3.  **查看**：计算完成后，**Data Mode** 自动增加并切换为 `Cross Correlation` 选项。

### 4.5 变分模态分解 (VMD Analysis)
V1.2 新增功能，用于信号的非线性、非平稳自适应分解。
1.  **启动**：点击工具栏 **Standard Analysis -> VMD Analysis**。
2.  **设置**：
    *   **Modes (K)**: 分解模态数量。
    *   **Alpha**: 带宽约束参数。
    *   **Tau**: 噪声容限。
    *   **Sliding Window**: 可选开启滑窗模式，用于处理大规模数据（支持并行计算）。
3.  **计算**：点击 OK，后台将异步进行计算（支持进度条显示和取消）。
4.  **查看**：
    *   计算完成后，**Data Mode** 自动增加并切换至 `VMD Mode`。
    *   **模态切换**：使用 Data Mode 下拉菜单右侧的 **Mode 选择器** 切换显示的模态 (Mode 1, Mode 2...)。
    *   **视图联动**：VMD 模式下，主视图显示当前模态的时空图，其余小视图分别显示该模态的时频图、频谱图和 FK 谱。
    *   **交互分析**：支持在模态图上进行框选回放、直方图对比度调节及剖面查看。

## 5. 项目结构 (Structure)
- `core/`: 核心算法库 (`DataProcessor`)，包含滤波、变换、正反演逻辑。
- `ui/`: 界面代码。
  - `main_window.py`: 主窗口逻辑（包含各类分析对话框）。
  - `node_editor/`: 节点编辑器组件。
- `utils/`: 通用工具函数。
- `main.py`: 程序入口。


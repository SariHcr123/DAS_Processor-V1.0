# DAS Processor V1.0

## 1. 软件简介 (Introduction)
DAS Processor 是一款专为分布式光纤传感（DAS）数据设计的处理与分析软件。它集成了数据加载、交互式预处理、多维度可视化以及高级信号分析功能。软件采用模块化设计，支持节点式处理流程编辑，能够高效完成从原始数据到地质参数反演的全流程分析。

## 2. 启动方式 (Running)
确保已安装 Python 环境及相关依赖库（PyQt5, numpy, scipy, matplotlib）。
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
*   **实时生效**：编辑完成后，主界面会自动应用当前的 Pipeline 对原始数据进行重计算。

### 3.3 可视化视图 (Visualization)
主界面右侧面板提供多种视图模式，支持通过下拉菜单切换：
*   **Data Mode**:
    *   `Processed Data`: 显示经过 Pipeline 处理后的时空数据。
    *   `Cross Correlation`: 显示互相关计算结果（需先运行互相关分析）。
*   **Analysis View**:
    *   `Standard View`: 默认视图，包含瀑布图、时间切片、空间切片及直方图。
    *   `Dispersion Analysis`: 频散能谱图。
    *   `Beamforming`: 波束形成能量图。
    *   `Velocity Analysis`: 速度反演结果图。

### 3.4 交互操作 (Interaction)
*   **播放回放**：在瀑布图上使用左键框选一个区域，会自动开始在该时间/空间范围内循环播放切片波形。
*   **视图切换**：点击不同的视图窗口（如 FK 谱、频谱图）可将其放大至主显示区。
*   **参数设置**：点击 **Settings** 可全局配置 dx, dt, Gauge Length 以及各分析模块的默认参数。

---

## 4. 高级分析操作指南 (Operation Guide)

### 4.1 频散分析 (Dispersion Analysis)
用于提取瑞利波/Scholte波的频散曲线。
1.  **启动**：点击工具栏 **Dispersion** 按钮。
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
2.  **启动**：点击工具栏 **Velocity Analysis** 按钮。
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
1.  **启动**：点击工具栏 **Beamforming** 按钮。
2.  **设置**：指定扫描角度范围、频率范围及介质声速。
3.  **查看**：结果将显示在 `Beamforming` 视图中，展示不同时间段的能量分布。图像已启用双线性插值平滑，视觉效果更佳。

### 4.4 互相关分析 (Cross Correlation)
用于计算参考道与其他所有道的互相关，常用于被动源干涉成像。
1.  **启动**：点击工具栏 **Cross Correlation**。
2.  **设置**：选择参考道索引 (Ref Channel) 和最大时延 (Max Lag)。
3.  **查看**：将 **Data Mode** 切换为 `Cross Correlation` 即可查看虚拟源记录。

## 5. 项目结构 (Structure)
- `core/`: 核心算法库 (`DataProcessor`)，包含滤波、变换、正反演逻辑。
- `ui/`: 界面代码。
  - `main_window.py`: 主窗口逻辑。
  - `node_editor/`: 节点编辑器组件。
  - `inversion_dialog.py`: 速度反演对话框。
- `utils/`: 通用工具函数。
- `main.py`: 程序入口。

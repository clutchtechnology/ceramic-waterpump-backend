# ============================================================
# 文件说明: parser_vib_db4.py - 振动传感器数据解析器 (DB4)
# ============================================================
# 专门用于解析 DB4 振动传感器数据 (6个传感器)
# 从 DB4 中提取 V(速度)/D(位移)/HZ(频率) 三组核心数据
# 输出与原 DB4 vibration 模块兼容的字段名 (VX/VY/VZ/DX/DY/DZ/HZX/HZY/HZZ)
# 字段定义内联在 config_vib_4_db4.yaml 中
# ============================================================

import struct
import yaml
from typing import Dict, List, Any
from pathlib import Path
from datetime import datetime


# DB4 字段名 -> 输出字段名 映射
# 将 DB4 config 中的 vel/dis_f/freq 字段映射为与 DB4 兼容的 VX/DX/HZX 命名
_FIELD_MAPPING = {
    # vel 模块 (速度) -> VX/VY/VZ
    "vel_x": "VX",
    "vel_y": "VY",
    "vel_z": "VZ",
    # dis_f 模块 (位移) -> DX/DY/DZ
    "dis_f_x": "DX",
    "dis_f_y": "DY",
    "dis_f_z": "DZ",
    # freq 模块 (频率) -> HZX/HZY/HZZ
    "freq_x": "HZX",
    "freq_y": "HZY",
    "freq_z": "HZZ",
}

# 需要合并为 vibration 模块的 module_type 列表
_VIBRATION_MODULES = {"vel", "dis_f", "freq"}


class VibDB4Parser:
    """振动传感器解析器 (DB4)
    
    从 DB4 中提取 6 个振动传感器的三组核心振动数据，合并为一个 vibration 模块输出:
    - vel (速度幅值) -> VX/VY/VZ
    - dis_f (位移幅值) -> DX/DY/DZ
    - freq (频率) -> HZX/HZY/HZZ
    
    其余模块 (accel/accel_f/reserved) 作为独立模块输出。
    """
    
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    
    def __init__(self, config_path: str = None):
        """初始化解析器
        
        Args:
            config_path: DB4 配置文件路径
        """
        self.config_path = Path(config_path) if config_path else self.PROJECT_ROOT / "configs" / "config_vib_4_db4.yaml"
        self.config = None
        self.load_config()
        
    def load_config(self):
        """加载配置"""
        try:
            if not self.config_path.exists():
                print(f"[Parser] DB4 配置文件不存在: {self.config_path}")
                return
                
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            
            db_num = self.config.get('db_number', 4)
            size = self.config.get('total_size', 228)
            device_count = len(self.config.get('devices', []))
            print(f"[Parser] VibDB4Parser 初始化完成: DB{db_num}, 总大小{size}字节, {device_count}个设备")
        except Exception as e:
            print(f"[Parser] VibDB4Parser 加载配置失败: {e}")

    def _parse_field_value(self, db_data: bytes, field: Dict[str, Any]) -> Any:
        """解析单个字段值（使用绝对偏移量）"""
        offset = field['offset']
        data_type = field['data_type']
        
        try:
            if data_type in ('Int', 'INT'):
                val = struct.unpack('>h', db_data[offset:offset+2])[0]
            elif data_type in ('Word', 'WORD'):
                val = struct.unpack('>H', db_data[offset:offset+2])[0]
            elif data_type in ('DInt', 'DINT'):
                val = struct.unpack('>i', db_data[offset:offset+4])[0]
            elif data_type in ('DWord', 'DWORD'):
                val = struct.unpack('>I', db_data[offset:offset+4])[0]
            elif data_type in ('Real', 'REAL'):
                val = struct.unpack('>f', db_data[offset:offset+4])[0]
            else:
                val = 0
                
            scale = field.get('scale', 1.0)
            if isinstance(val, (int, float)):
                val = val * scale
            return val
        except Exception:
            return 0

    def _parse_module_fields(self, module_info: Dict, db_data: bytes) -> Dict[str, Any]:
        """解析单个模块的所有字段（返回原始 field dict）"""
        offset = module_info['offset']
        size = module_info['size']
        
        if offset + size > len(db_data):
            print(f"[Parser] 模块偏移越界: {module_info['module_type']} (offset {offset}, size {size})")
            return {}
        
        parsed_fields = {}
        for field in module_info.get('fields', []):
            val = self._parse_field_value(db_data, field)
            field_name = field['name']
            parsed_fields[field_name] = {
                'value': val,
                'display_name': field.get('display_name', field_name),
                'unit': field.get('unit', '')
            }
        return parsed_fields

    def _parse_device(self, device_config: Dict, db_data: bytes) -> Dict[str, Any]:
        """解析单个设备的所有模块
        
        将 vel/dis_f/freq 三个模块合并为一个 vibration 模块输出,
        字段名映射为 VX/VY/VZ/DX/DY/DZ/HZX/HZY/HZZ (与原 DB4 兼容)。
        其余模块独立输出。
        """
        device_result = {
            'device_id': device_config['device_id'],
            'device_name': device_config['device_name'],
            'device_type': device_config['device_type'],
            'timestamp': datetime.now().isoformat(),
            'modules': {}
        }
        
        # 1. 收集 vibration 三组核心数据 (vel/dis_f/freq -> 合并为 vibration)
        vibration_fields = {}
        
        for module in device_config.get('modules', []):
            module_type = module['module_type']
            parsed = self._parse_module_fields(module, db_data)
            if not parsed:
                continue
                
            if module_type in _VIBRATION_MODULES:
                # 合并到 vibration，字段名映射为 VX/DX/HZX 等
                for raw_name, field_info in parsed.items():
                    mapped_name = _FIELD_MAPPING.get(raw_name, raw_name)
                    vibration_fields[mapped_name] = field_info
            else:
                # 其余模块独立输出
                device_result['modules'][module_type] = {
                    'module_type': module_type,
                    'description': module.get('description', ''),
                    'fields': parsed
                }
        
        # 2. 将合并后的 vibration 模块加入结果
        if vibration_fields:
            device_result['modules']['vibration'] = {
                'module_type': 'vibration',
                'description': '振动传感器核心数据 (速度/位移/频率)',
                'fields': vibration_fields
            }
            
        return device_result

    def parse_all(self, db_data: bytes) -> List[Dict[str, Any]]:
        """解析所有设备数据
        
        返回 6 个设备的数据列表
        """
        if not self.config:
            return []
        
        results = []
        for device_config in self.config.get('devices', []):
            device_result = self._parse_device(device_config, db_data)
            results.append(device_result)
        
        return results

    def get_device_list(self) -> List[Dict[str, str]]:
        """获取设备基本信息"""
        if not self.config:
            return []
        
        devices = []
        for device_config in self.config.get('devices', []):
            devices.append({
                'device_id': device_config['device_id'],
                'device_name': device_config['device_name'],
                'device_type': device_config['device_type'],
                'category': 'vibration'
            })
        return devices


# 全局单例实例
_parser_instance: VibDB4Parser | None = None


def parse_vib_db4(raw_bytes: bytes) -> List[Dict[str, Any]]:
    """解析 DB4 振动数据块 (便捷函数)
    
    Args:
        raw_bytes: DB4 原始字节数据
    
    Returns:
        解析结果列表
    """
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = VibDB4Parser()
    return _parser_instance.parse_all(raw_bytes)

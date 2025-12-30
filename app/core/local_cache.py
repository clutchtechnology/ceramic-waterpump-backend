# ============================================================
# 文件说明: local_cache.py - 本地 SQLite 降级缓存
# ============================================================
# 当 InfluxDB 不可用时，数据暂存到本地 SQLite
# InfluxDB 恢复后自动重试写入
# ============================================================

import sqlite3
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

from config import get_settings

settings = get_settings()

# 缓存文件路径
CACHE_DB_PATH = Path(settings.local_cache_path if hasattr(settings, 'local_cache_path') else "data/cache.db")


@dataclass
class CachedPoint:
    """缓存的数据点"""
    measurement: str
    tags: Dict[str, str]
    fields: Dict[str, Any]
    timestamp: str  # ISO 格式
    retry_count: int = 0
    created_at: str = ""
    
    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'CachedPoint':
        data = json.loads(json_str)
        return cls(**data)


class LocalCache:
    """本地 SQLite 缓存管理器"""
    
    _instance: Optional['LocalCache'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._conn: Optional[sqlite3.Connection] = None
        self._db_lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """初始化 SQLite 数据库"""
        CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        self._conn = sqlite3.connect(str(CACHE_DB_PATH), check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                measurement TEXT NOT NULL,
                data_json TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_retry_at TEXT
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_measurement ON pending_points(measurement)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at ON pending_points(created_at)
        """)
        self._conn.commit()
        
        # 统计待处理数据
        cursor = self._conn.execute("SELECT COUNT(*) FROM pending_points")
        count = cursor.fetchone()[0]
        if count > 0:
            print(f"⚠️ 本地缓存有 {count} 条待写入数据")
    
    def save_points(self, points: List[CachedPoint]) -> int:
        """
        保存数据点到本地缓存
        
        Args:
            points: 数据点列表
        
        Returns:
            成功保存的数量
        """
        if not points:
            return 0
        
        with self._db_lock:
            try:
                now = datetime.now(timezone.utc).isoformat()
                data = [
                    (p.measurement, p.to_json(), p.retry_count, now)
                    for p in points
                ]
                self._conn.executemany(
                    "INSERT INTO pending_points (measurement, data_json, retry_count, created_at) VALUES (?, ?, ?, ?)",
                    data
                )
                self._conn.commit()
                return len(points)
            except Exception as e:
                print(f"❌ 本地缓存保存失败: {e}")
                return 0
    
    def get_pending_points(self, limit: int = 100, max_retry: int = 5) -> List[tuple]:
        """
        获取待重试的数据点
        
        Args:
            limit: 最大获取数量
            max_retry: 最大重试次数
        
        Returns:
            [(id, CachedPoint), ...]
        """
        with self._db_lock:
            try:
                cursor = self._conn.execute(
                    """
                    SELECT id, data_json FROM pending_points 
                    WHERE retry_count < ? 
                    ORDER BY created_at ASC 
                    LIMIT ?
                    """,
                    (max_retry, limit)
                )
                results = []
                for row in cursor.fetchall():
                    try:
                        point = CachedPoint.from_json(row[1])
                        results.append((row[0], point))
                    except Exception:
                        pass
                return results
            except Exception as e:
                print(f"❌ 读取本地缓存失败: {e}")
                return []
    
    def mark_success(self, ids: List[int]):
        """标记数据点写入成功（删除）"""
        if not ids:
            return
        
        with self._db_lock:
            try:
                placeholders = ",".join("?" * len(ids))
                self._conn.execute(
                    f"DELETE FROM pending_points WHERE id IN ({placeholders})",
                    ids
                )
                self._conn.commit()
            except Exception as e:
                print(f"❌ 删除缓存记录失败: {e}")
    
    def mark_retry(self, ids: List[int]):
        """标记数据点需要重试（增加重试计数）"""
        if not ids:
            return
        
        with self._db_lock:
            try:
                now = datetime.now(timezone.utc).isoformat()
                placeholders = ",".join("?" * len(ids))
                self._conn.execute(
                    f"""
                    UPDATE pending_points 
                    SET retry_count = retry_count + 1, last_retry_at = ? 
                    WHERE id IN ({placeholders})
                    """,
                    [now] + ids
                )
                self._conn.commit()
            except Exception as e:
                print(f"❌ 更新重试计数失败: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._db_lock:
            try:
                cursor = self._conn.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN retry_count >= 5 THEN 1 ELSE 0 END) as failed,
                        MIN(created_at) as oldest
                    FROM pending_points
                """)
                row = cursor.fetchone()
                return {
                    "pending_count": row[0] or 0,
                    "failed_count": row[1] or 0,
                    "oldest_record": row[2]
                }
            except Exception:
                return {"pending_count": 0, "failed_count": 0, "oldest_record": None}
    
    def cleanup_old(self, days: int = 7):
        """清理超过指定天数的失败记录"""
        with self._db_lock:
            try:
                from datetime import timedelta
                cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
                cursor = self._conn.execute(
                    "DELETE FROM pending_points WHERE created_at < ? AND retry_count >= 5",
                    (cutoff,)
                )
                deleted = cursor.rowcount
                self._conn.commit()
                if deleted > 0:
                    print(f"🧹 清理了 {deleted} 条过期缓存记录")
            except Exception as e:
                print(f"❌ 清理缓存失败: {e}")
    
    def close(self):
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None


# 全局单例
def get_local_cache() -> LocalCache:
    return LocalCache()

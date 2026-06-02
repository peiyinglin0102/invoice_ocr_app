# -*- coding: utf-8 -*-
import os
import json
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Fallback local JSON database file
LOCAL_DB_FILE = "local_db.json"

class DatabaseManager:
    """
    資料庫管理器。
    支援 MongoDB Atlas 雲端資料庫；若未設定 `MONGO_URI` 或連線失敗，
    則自動優雅降級為本地 `local_db.json` 檔案資料庫進行持久化儲存。
    """

    def __init__(self):
        self.use_mongodb = False
        self.client = None
        self.db = None
        
        # 讀取連線字串（優先使用 Streamlit Secrets，若無則嘗試環境變數）
        self.mongo_uri = ""
        try:
            import streamlit as st
            if "MONGO_URI" in st.secrets:
                self.mongo_uri = st.secrets["MONGO_URI"].strip()
        except Exception:
            pass

        if not self.mongo_uri:
            self.mongo_uri = os.getenv("MONGO_URI", "").strip()

        if self.mongo_uri:
            try:
                from pymongo import MongoClient
                # 設定連線逾時為 3 秒以利快速切換至備援
                self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=3000)
                # 測試連線
                self.client.admin.command('ping')
                self.db = self.client["invoice_ocr_db"]
                self.use_mongodb = True
                logger.info("Successfully connected to MongoDB Atlas!")
            except Exception as e:
                logger.warning(f"MongoDB connection failed: {e}. Falling back to Local JSON Database.")
                self.use_mongodb = False
        else:
            logger.info("No MONGO_URI provided. Using Local JSON Database as fallback.")
            self.use_mongodb = False

        if not self.use_mongodb:
            self._init_local_db()

    # ─────────────────────────────────────────────
    # 本地 JSON 資料庫輔助方法
    # ─────────────────────────────────────────────
    def _init_local_db(self):
        if not os.path.exists(LOCAL_DB_FILE):
            with open(LOCAL_DB_FILE, "w", encoding="utf-8") as f:
                json.dump({"trips": [], "invoices": []}, f, ensure_ascii=False, indent=2)

    def _read_local_db(self) -> Dict[str, List[Dict[str, Any]]]:
        self._init_local_db()
        try:
            with open(LOCAL_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading local db: {e}")
            return {"trips": [], "invoices": []}

    def _write_local_db(self, data: Dict[str, List[Dict[str, Any]]]):
        try:
            with open(LOCAL_DB_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error writing local db: {e}")

    # ─────────────────────────────────────────────
    # 旅遊專案 (Trip) CRUD
    # ─────────────────────────────────────────────
    def get_trips(self) -> List[Dict[str, Any]]:
        """取得所有旅遊專案，依時間排序"""
        if self.use_mongodb:
            try:
                trips = list(self.db["trips"].find({}, {"_id": 0}))
                # 按建立時間排序
                return sorted(trips, key=lambda x: x.get("created_at", ""), reverse=True)
            except Exception as e:
                logger.error(f"MongoDB error in get_trips: {e}")
                # 失敗時暫時讀取本地備援
                return self._read_local_db()["trips"]
        else:
            data = self._read_local_db()
            return sorted(data["trips"], key=lambda x: x.get("created_at", ""), reverse=True)

    def create_trip(self, name: str, start_date: str, end_date: str, base_currency: str, budget_twd: float) -> Dict[str, Any]:
        """建立新的旅遊專案"""
        trip = {
            "trip_id": str(uuid.uuid4()),
            "trip_name": name.strip(),
            "start_date": start_date.strip(),
            "end_date": end_date.strip(),
            "base_currency": base_currency.strip().upper(),
            "budget_twd": float(budget_twd),
            "created_at": datetime.utcnow().isoformat() + "Z"
        }

        if self.use_mongodb:
            try:
                self.db["trips"].insert_one(trip.copy())
            except Exception as e:
                logger.error(f"MongoDB error in create_trip: {e}")
                # 寫入本地作為備用
                data = self._read_local_db()
                data["trips"].append(trip)
                self._write_local_db(data)
        else:
            data = self._read_local_db()
            data["trips"].append(trip)
            self._write_local_db(data)
        return trip

    # ─────────────────────────────────────────────
    # 發票明細 (Invoice) CRUD
    # ─────────────────────────────────────────────
    def get_invoices(self, trip_id: str) -> List[Dict[str, Any]]:
        """取得指定旅遊專案下的所有發票明細"""
        if self.use_mongodb:
            try:
                invoices = list(self.db["invoices"].find({"trip_id": trip_id}, {"_id": 0}))
                return sorted(invoices, key=lambda x: x.get("uploaded_at", ""))
            except Exception as e:
                logger.error(f"MongoDB error in get_invoices: {e}")
                # 失敗時讀取本地備用
                data = self._read_local_db()
                return [inv for inv in data["invoices"] if inv.get("trip_id") == trip_id]
        else:
            data = self._read_local_db()
            invoices = [inv for inv in data["invoices"] if inv.get("trip_id") == trip_id]
            return sorted(invoices, key=lambda x: x.get("uploaded_at", ""))

    def save_invoice(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """保存發票文檔"""
        if "invoice_id" not in invoice_data:
            invoice_data["invoice_id"] = str(uuid.uuid4())
        if "uploaded_at" not in invoice_data:
            invoice_data["uploaded_at"] = datetime.utcnow().isoformat() + "Z"

        if self.use_mongodb:
            try:
                # 移除 _id 確保乾淨插入
                invoice_doc = invoice_data.copy()
                invoice_doc.pop("_id", None)
                self.db["invoices"].insert_one(invoice_doc)
            except Exception as e:
                logger.error(f"MongoDB error in save_invoice: {e}")
                data = self._read_local_db()
                data["invoices"].append(invoice_data)
                self._write_local_db(data)
        else:
            data = self._read_local_db()
            data["invoices"].append(invoice_data)
            self._write_local_db(data)
        return invoice_data

    def delete_invoice(self, invoice_id: str):
        """刪除指定發票"""
        if self.use_mongodb:
            try:
                self.db["invoices"].delete_one({"invoice_id": invoice_id})
            except Exception as e:
                logger.error(f"MongoDB error in delete_invoice: {e}")
                data = self._read_local_db()
                data["invoices"] = [inv for inv in data["invoices"] if inv.get("invoice_id") != invoice_id]
                self._write_local_db(data)
        else:
            data = self._read_local_db()
            data["invoices"] = [inv for inv in data["invoices"] if inv.get("invoice_id") != invoice_id]
            self._write_local_db(data)

    def update_invoice_items(self, invoice_id: str, new_items: List[Dict[str, Any]], new_foreign_total: float, new_twd_total: float):
        """更新單張發票的品項明細與加總"""
        if self.use_mongodb:
            try:
                self.db["invoices"].update_one(
                    {"invoice_id": invoice_id},
                    {
                        "$set": {
                            "purchase_details": new_items,
                            "total_foreign_amount": float(new_foreign_total),
                            "total_twd": float(new_twd_total)
                        }
                    }
                )
            except Exception as e:
                logger.error(f"MongoDB error in update_invoice_items: {e}")
                self._update_local_invoice_items(invoice_id, new_items, new_foreign_total, new_twd_total)
        else:
            self._update_local_invoice_items(invoice_id, new_items, new_foreign_total, new_twd_total)

    def _update_local_invoice_items(self, invoice_id: str, new_items: List[Dict[str, Any]], new_foreign_total: float, new_twd_total: float):
        data = self._read_local_db()
        updated = False
        for inv in data["invoices"]:
            if inv.get("invoice_id") == invoice_id:
                inv["purchase_details"] = new_items
                inv["total_foreign_amount"] = float(new_foreign_total)
                inv["total_twd"] = float(new_twd_total)
                updated = True
                break
        if updated:
            self._write_local_db(data)

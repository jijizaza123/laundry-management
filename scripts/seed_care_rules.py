"""洗护知识库种子数据（幂等：按 fabric 覆盖写入）

出处只用两类：国家标准/行业标准的规范名 + 门店现行价目表。
不写具体条款号，避免"引用了但其实没这条"的假依据。
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.services import care_service  # noqa: E402

GB_SYMBOL = "GB/T 8685《纺织品 维护标签规范 符号法》"
FZ_CASHMERE = "FZ/T 73009《羊绒针织品》"
GB_DOWN = "GB/T 14272《羽绒服装》"
GB_SILK = "GB/T 15551《桑蚕丝织物》"

RULES = [
    {
        "fabric": "羊绒",
        "aliases": "开司米,cashmere,羊绒衫,羊绒大衣",
        "water_wash": "不可水洗",
        "service": "干洗",
        "avoid": "不可机洗;不可拧干;不可悬挂晾晒;不可用碱性洗涤剂",
        "reason": "羊绒纤维表面有鳞片结构，水洗加机械揉搓会缩绒、起球、变形，且湿态强度低易拉长",
        "source": GB_SYMBOL + "；" + FZ_CASHMERE,
    },
    {
        "fabric": "羊毛",
        "aliases": "毛料,毛呢,wool,羊毛衫,西装面料",
        "water_wash": "不可水洗",
        "service": "干洗",
        "avoid": "不可热水洗涤;不可甩干;不可高温熨烫",
        "reason": "羊毛同样会缩绒毡化，热水与机械力会让衣物整体缩小一号且无法恢复",
        "source": GB_SYMBOL,
    },
    {
        "fabric": "真丝",
        "aliases": "桑蚕丝,丝质,silk,丝绸,真丝裙",
        "water_wash": "仅手洗",
        "service": "干洗",
        "avoid": "不可机洗;不可拧绞;不可暴晒;不可用碱性洗涤剂",
        "reason": "蚕丝蛋白耐酸不耐碱，碱性洗涤剂会损伤光泽；湿态强度低，拧绞易断丝、易起水渍",
        "source": GB_SYMBOL + "；" + GB_SILK,
    },
    {
        "fabric": "羽绒",
        "aliases": "羽绒服,鸭绒,鹅绒,down",
        "water_wash": "可水洗",
        "service": "普通洗",
        "avoid": "不建议干洗;不可拧干;不可暴晒;不可高温烘干",
        "reason": "干洗溶剂会洗掉羽绒表面的天然油脂，蓬松度下降影响保暖；需中性洗涤剂、轻柔程序并彻底漂洗",
        "source": GB_DOWN + "；" + GB_SYMBOL,
    },
    {
        "fabric": "棉",
        "aliases": "棉质,纯棉,cotton,棉麻,亚麻",
        "water_wash": "可水洗",
        "service": "普通洗",
        "avoid": "深色首次单独洗;不可长时间浸泡;不可高温烘干",
        "reason": "棉纤维吸湿性强但缩水率较高，长时间浸泡和高温烘干容易缩水、掉色",
        "source": GB_SYMBOL,
    },
    {
        "fabric": "化纤",
        "aliases": "涤纶,聚酯纤维,polyester,锦纶,尼龙",
        "water_wash": "可水洗",
        "service": "普通洗",
        "avoid": "不可高温熨烫;不可高温烘干",
        "reason": "化纤属热塑性纤维，高温会软化变形甚至烫出亮痕",
        "source": GB_SYMBOL,
    },
    {
        "fabric": "皮革",
        "aliases": "真皮,皮衣,皮草,裘皮,leather",
        "water_wash": "不可水洗",
        "service": "精洗",
        "avoid": "不可水洗;不可自行晾晒;不可用普通洗涤剂",
        "reason": "水洗会让皮革脱脂变硬、开裂、掉色，需要专用皮革护理工艺",
        "source": "GB/T 8685 洗涤符号体系；门店皮革护理作业规范",
    },
    {
        "fabric": "蕾丝",
        "aliases": "雪纺,薄纱,lace,chiffon",
        "water_wash": "仅手洗",
        "service": "精洗",
        "avoid": "不可机洗;不可用力搓洗;不可拧干",
        "reason": "组织稀疏、纱线细，机械力容易勾丝破洞，建议装洗衣袋轻柔手洗或专业精洗",
        "source": GB_SYMBOL,
    },
    {
        "fabric": "牛仔",
        "aliases": "denim,牛仔裤,丹宁",
        "water_wash": "可水洗",
        "service": "普通洗",
        "avoid": "建议翻面冷水洗;不可频繁水洗;不可高温烘干",
        "reason": "靛蓝染料易掉色，翻面冷水可减少褪色；频繁水洗会加速做旧效果流失",
        "source": GB_SYMBOL,
    },
    {
        "fabric": "西装",
        "aliases": "西服,礼服,正装,suits",
        "water_wash": "不可水洗",
        "service": "干洗",
        "avoid": "不可水洗;不可机洗;不可悬挂暴晒",
        "reason": "内有粘合衬与定型结构，水洗会导致起泡、变形，只能干洗并配合熨烫定型",
        "source": GB_SYMBOL,
    },
]


def main() -> int:
    Base.metadata.create_all(bind=engine)  # care_rules 是新表，可直接建
    db = SessionLocal()
    try:
        for payload in RULES:
            care_service.upsert(db, payload)
        rows = care_service.list_rules(db)
        print(f"[+] 洗护规则已写入 {len(rows)} 条")
        for row in rows:
            print(f"    - {row['fabric']}（{row['water_wash']} / 建议 {row['service']}）")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

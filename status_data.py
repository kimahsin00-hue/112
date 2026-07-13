"""축복/에다니아 제보 시스템이 참조하는 정적 데이터."""

STATUS_KIND_OPTIONS = {
    "blessing": ["해축", "달축", "땅축"],
    "edana": ["아에테리온", "님파마레", "오르비타", "테네브라움", "제피로스"],
}

STATUS_SERVER_REGIONS = ["발레노스"]

# 모든 서버 공통으로 1~3번 채널 중 선택
STATUS_SERVER_NUMBERS = {region: ["1", "2", "3"] for region in STATUS_SERVER_REGIONS}

STATUS_DEFAULT_MINUTES = {"blessing": 180, "edana": 60}
STATUS_TITLES = {"blessing": "아침의 축복", "edana": "에다니아"}

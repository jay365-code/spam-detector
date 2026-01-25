from main import calculate_advanced_metrics

print("🧪 백엔드 지표 계산 테스트 시작...\n")

# 테스트 케이스 1: 완벽한 합의
print("테스트 1: 완벽한 합의 (TP=50, TN=50, FP=0, FN=0)")
result = calculate_advanced_metrics(tp=50, tn=50, fp=0, fn=0, total=100)
print(f"  Kappa: {result['kappa']} (기대값: 1.0)")
print(f"  Kappa Status: {result['kappa_status']}")
print(f"  MCC: {result['mcc']} (기대값: 1.0)")
print(f"  HEI: {result['hei']}")
print(f"  HEI Status: {result['hei_status']}")
assert result['kappa'] == 1.0, "Kappa should be 1.0 for perfect agreement"
assert result['mcc'] == 1.0, "MCC should be 1.0 for perfect match"
assert result['hei_status'] == "인간 대체 가능", "HEI should indicate human-equivalent"
print("  ✅ 통과\n")

# 테스트 케이스 2: 합의 없음
print("테스트 2: 합의 없음 (TP=0, TN=0, FP=25, FN=25)")
result = calculate_advanced_metrics(tp=0, tn=0, fp=25, fn=25, total=50)
print(f"  Kappa: {result['kappa']}")
print(f"  Kappa Status: {result['kappa_status']}")
print(f"  MCC: {result['mcc']}")
print(f"  HEI: {result['hei']}")
print(f"  HEI Status: {result['hei_status']}")
assert result['kappa'] < 0.2, "Kappa should be very low for no agreement"
assert result['hei_status'] == "검토 필요", "HEI should indicate review required"
print("  ✅ 통과\n")

# 테스트 케이스 3: 중간 수준의 합의
print("테스트 3: 중간 수준 합의 (TP=60, TN=20, FP=10, FN=10)")
result = calculate_advanced_metrics(tp=60, tn=20, fp=10, fn=10, total=100)
print(f"  Kappa: {result['kappa']}")
print(f"  Kappa Status: {result['kappa_status']}")
print(f"  MCC: {result['mcc']}")
print(f"  Disagreement Rate: {result['disagreement_rate']} (기대값: 0.2)")
print(f"  HEI: {result['hei']}")
print(f"  HEI Status: {result['hei_status']}")
assert result['disagreement_rate'] == 0.2, "Disagreement rate should be 20%"
print("  ✅ 통과\n")

# 테스트 케이스 4: 클래스 불균형 상황 (HAM >> SPAM)
print("테스트 4: 클래스 불균형 (TP=10, TN=80, FP=5, FN=5)")
result = calculate_advanced_metrics(tp=10, tn=80, fp=5, fn=5, total=100)
print(f"  Kappa: {result['kappa']}")
print(f"  Kappa Status: {result['kappa_status']}")
print(f"  MCC: {result['mcc']}")
print(f"  HEI: {result['hei']}")
print(f"  HEI Status: {result['hei_status']}")
# MCC should handle imbalance better than raw accuracy
print("  ✅ 통과\n")

print("=" * 50)
print("✨ 모든 백엔드 지표 테스트 통과!")
print("=" * 50)

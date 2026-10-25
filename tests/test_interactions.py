import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
from interactions import check_patient, load_seed
T = load_seed(str(pathlib.Path(__file__).parent.parent / "data" / "interactions_seed.csv"))
M = lambda i, d, s="active": {"id": i, "display": d, "status": s}

def test_finds_known_pair():
    a = check_patient("p", [M("1", "Simvastatin 20 MG Oral Tablet"), M("2", "amLODIPine 2.5 MG Oral Tablet")], T)
    assert len(a) == 1 and set(a[0].med_ids) == {"1", "2"}

def test_ignores_completed_orders():
    assert check_patient("p", [M("1", "Warfarin Sodium 5 MG Oral Tablet"), M("2", "aspirin 81 MG Oral Tablet", "completed")], T) == []

def test_combination_product_matches_each_ingredient():
    a = check_patient("p", [M("1", "hydrochlorothiazide 12.5 MG / lisinopril 20 MG Oral Tablet"), M("2", "Naproxen sodium 220 MG Oral Tablet")], T)
    assert [x.ingredient_a for x in a] == ["lisinopril"]

def test_insulin_mixture_and_beta_blocker():
    a = check_patient("p", [M("1", "insulin isophane, human 70 UNT/ML / insulin, regular, human 30 UNT/ML Injectable Suspension [Humulin]"),
                            M("2", "24 HR metoprolol succinate 100 MG Extended Release Oral Tablet")], T)
    assert len(a) == 1 and a[0].severity == "Moderate"

def test_no_partial_word_match():
    assert check_patient("p", [M("1", "Simvastatin 20 MG"), M("2", "amlodipinexyz")], T) == []

def test_no_self_interaction_within_one_order():
    assert check_patient("p", [M("1", "warfarin aspirin combo")], T) == []

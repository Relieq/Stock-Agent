from services.api.app import change_parts, short_name


def test_chieu_thay_doi_de_to_mau():
    assert change_parts("+203,7% (từ 1.209 tỷ lên 3.671 tỷ)") == {
        "cls": "pos", "main": "+203,7%", "rest": "từ 1.209 tỷ lên 3.671 tỷ"}
    assert change_parts("−17,1% (từ 16.625 tỷ xuống 13.789 tỷ)")["cls"] == "neg"
    assert change_parts("chuyển từ lỗ 5,0 tỷ sang lãi 3,0 tỷ")["cls"] == "pos"
    assert change_parts("chuyển từ lãi 5,0 tỷ sang lỗ 3,0 tỷ")["cls"] == "neg"
    assert change_parts("lỗ thu hẹp từ 9,0 tỷ còn 2,0 tỷ")["cls"] == "pos"
    assert change_parts("lỗ tăng từ 2,0 tỷ lên 9,0 tỷ")["cls"] == "neg"
    assert change_parts("cùng kỳ bằng 0, kỳ này 3,0 tỷ")["cls"] == "flat"
    assert change_parts("")["main"] == "" and change_parts(None)["cls"] == ""


def test_ten_cong_ty_gon():
    assert short_name("Ngân hàng Thương mại Cổ phần Á Châu") == "Ngân hàng Á Châu"
    assert short_name("Công ty Cổ phần Tập đoàn Masan") == "Tập đoàn Masan"
    assert short_name("Tổng Công ty Khí Việt Nam - Công ty Cổ phần") == "Tổng Công ty Khí Việt Nam"
    assert short_name("Công ty Cổ phần - Tổng Công ty Lọc Hóa dầu Việt Nam") == "Tổng Công ty Lọc Hóa dầu Việt Nam"
    assert short_name("CTCP Tasco") == "Tasco"
    assert short_name("Công ty Cổ phần FPT") == "FPT"

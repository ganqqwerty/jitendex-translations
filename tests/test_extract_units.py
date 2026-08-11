from jitendex_ru.extract_units import protected_tokens


def test_scalar_protected_tokens_are_available_to_the_model_and_validator():
    assert protected_tokens("example", "Press Ctrl+Alt+Del") == ("Ctrl+Alt+Del",)
    assert protected_tokens("note", 'Thai: "khao man kai"') == ("khao man kai",)
    assert protected_tokens(
        "xref_gloss", "Japanese sea bass (Lateolabrax japonicus)"
    ) == ("Lateolabrax japonicus",)


def test_common_xref_phrases_are_not_mistaken_for_taxa():
    assert protected_tokens("xref_gloss", "washi; Japanese paper") == ()
    assert protected_tokens("xref_gloss", "Morse code (esp. signalling)") == ()
    assert protected_tokens("xref_gloss", "Akihabara style; nerdy") == ()
    assert protected_tokens(
        "xref_gloss",
        "③ government office related to finances (Kamakura and Muromachi periods)",
    ) == ()

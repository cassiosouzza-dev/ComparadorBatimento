def validar_aih(aih: str) -> bool:
    """
    Verifica a validade de uma AIH utilizando a regra de Módulo 11 do DATASUS.
    """
    # Verifica o comprimento estrito e se contém apenas números
    if not isinstance(aih, str) or len(aih) != 13 or not aih.isdigit():
        return False

    # Separa o corpo numérico do dígito verificador
    base_numerica = int(aih[:12])
    digito_informado = int(aih[12])

    # Executa o cálculo de congruência (Módulo 11)
    resto = base_numerica % 11

    # O DATASUS define que restos iguais a 10 são convertidos para o dígito 0
    digito_esperado = 0 if resto == 10 else resto

    return digito_informado == digito_esperado
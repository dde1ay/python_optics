def clear_merit_function(mfe):
    count = int(mfe.NumberOfOperands)
    if count > 0:
        mfe.RemoveOperandsAt(1, count)


def add_merit_operand(mfe, zosapi, operand_name, target, weight=1.0):
    operand_type = getattr(zosapi.Editors.MFE.MeritOperandType, operand_name)
    operand = mfe.AddOperand()
    operand.ChangeType(operand_type)
    operand.Target = target
    operand.Weight = weight
    return operand

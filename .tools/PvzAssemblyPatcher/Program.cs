using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Text.Json;

static IEnumerable<TypeDefinition> EnumerateTypes(IEnumerable<TypeDefinition> types)
{
    foreach (var type in types)
    {
        yield return type;
        foreach (var nested in EnumerateTypes(type.NestedTypes))
        {
            yield return nested;
        }
    }
}

static bool ContainsCjk(string value)
{
    return value.Any(character =>
        character is >= '\u3000' and <= '\u303f' or
        >= '\u3400' and <= '\u9fff' or
        >= '\uf900' and <= '\ufaff' or
        >= '\uff01' and <= '\uff60');
}

static string InstructionOperandSignature(
    Instruction instruction,
    MethodDefinition method)
{
    if (instruction.OpCode == OpCodes.Ldstr)
    {
        return "<localized-string>";
    }

    return instruction.Operand switch
    {
        null => "",
        Instruction target =>
            $"instruction:{method.Body.Instructions.IndexOf(target)}",
        Instruction[] targets =>
            "instructions:" + string.Join(
                ",",
                targets.Select(target =>
                    method.Body.Instructions.IndexOf(target))),
        VariableDefinition variable =>
            $"variable:{variable.Index}:{variable.VariableType.FullName}",
        ParameterDefinition parameter =>
            $"parameter:{parameter.Index}:{parameter.ParameterType.FullName}",
        MethodReference reference => $"method:{reference.FullName}",
        FieldReference reference => $"field:{reference.FullName}",
        TypeReference reference => $"type:{reference.FullName}",
        CallSite callSite => $"callsite:{callSite.FullName}",
        string value => $"string:{value}",
        _ => $"{instruction.Operand.GetType().FullName}:{instruction.Operand}",
    };
}

static int InstructionIndex(MethodDefinition method, Instruction? instruction)
{
    return instruction is null ? -1 : method.Body.Instructions.IndexOf(instruction);
}

static string ExceptionHandlerSignature(
    ExceptionHandler handler,
    MethodDefinition method)
{
    return string.Join(
        ":",
        handler.HandlerType,
        handler.CatchType?.FullName ?? "",
        InstructionIndex(method, handler.TryStart),
        InstructionIndex(method, handler.TryEnd),
        InstructionIndex(method, handler.HandlerStart),
        InstructionIndex(method, handler.HandlerEnd),
        InstructionIndex(method, handler.FilterStart));
}

static IReadOnlyList<string> CompareAssemblyLogic(
    AssemblyDefinition baseline,
    AssemblyDefinition localized,
    out int localizedStringInstructionCount,
    out int changedStringInstructionCount)
{
    var differences = new List<string>();
    localizedStringInstructionCount = 0;
    changedStringInstructionCount = 0;

    var baselineTypes = EnumerateTypes(baseline.MainModule.Types)
        .ToDictionary(type => type.FullName);
    var localizedTypes = EnumerateTypes(localized.MainModule.Types)
        .ToDictionary(type => type.FullName);
    foreach (var missing in baselineTypes.Keys.Except(localizedTypes.Keys).Order())
    {
        differences.Add($"Missing type: {missing}");
    }
    foreach (var added in localizedTypes.Keys.Except(baselineTypes.Keys).Order())
    {
        differences.Add($"Added type: {added}");
    }

    foreach (var typeName in baselineTypes.Keys.Intersect(localizedTypes.Keys).Order())
    {
        var baselineType = baselineTypes[typeName];
        var localizedType = localizedTypes[typeName];
        if (baselineType.Attributes != localizedType.Attributes)
        {
            differences.Add($"Type attributes changed: {typeName}");
        }

        var baselineFields = baselineType.Fields
            .ToDictionary(field => field.FullName);
        var localizedFields = localizedType.Fields
            .ToDictionary(field => field.FullName);
        if (!baselineFields.Keys.Order().SequenceEqual(localizedFields.Keys.Order()))
        {
            differences.Add($"Field set changed: {typeName}");
        }
        else
        {
            foreach (var fieldName in baselineFields.Keys)
            {
                var left = baselineFields[fieldName];
                var right = localizedFields[fieldName];
                if (left.Attributes != right.Attributes ||
                    left.HasConstant != right.HasConstant ||
                    !Equals(left.Constant, right.Constant))
                {
                    differences.Add($"Field metadata changed: {fieldName}");
                }
            }
        }

        var baselineProperties = baselineType.Properties
            .Select(property => property.FullName)
            .Order()
            .ToArray();
        var localizedProperties = localizedType.Properties
            .Select(property => property.FullName)
            .Order()
            .ToArray();
        if (!baselineProperties.SequenceEqual(localizedProperties))
        {
            differences.Add($"Property set changed: {typeName}");
        }

        var baselineEvents = baselineType.Events
            .Select(eventDefinition => eventDefinition.FullName)
            .Order()
            .ToArray();
        var localizedEvents = localizedType.Events
            .Select(eventDefinition => eventDefinition.FullName)
            .Order()
            .ToArray();
        if (!baselineEvents.SequenceEqual(localizedEvents))
        {
            differences.Add($"Event set changed: {typeName}");
        }

        var baselineMethods = baselineType.Methods
            .ToDictionary(method => method.FullName);
        var localizedMethods = localizedType.Methods
            .ToDictionary(method => method.FullName);
        foreach (var missing in baselineMethods.Keys.Except(localizedMethods.Keys).Order())
        {
            differences.Add($"Missing method: {missing}");
        }
        foreach (var added in localizedMethods.Keys.Except(baselineMethods.Keys).Order())
        {
            differences.Add($"Added method: {added}");
        }

        foreach (var methodName in baselineMethods.Keys.Intersect(localizedMethods.Keys).Order())
        {
            var left = baselineMethods[methodName];
            var right = localizedMethods[methodName];
            if (left.Attributes != right.Attributes ||
                left.ImplAttributes != right.ImplAttributes ||
                left.CallingConvention != right.CallingConvention ||
                left.GenericParameters.Count != right.GenericParameters.Count ||
                left.HasBody != right.HasBody)
            {
                differences.Add($"Method metadata changed: {methodName}");
                continue;
            }
            if (!left.HasBody)
            {
                continue;
            }

            var leftBody = left.Body;
            var rightBody = right.Body;
            if (leftBody.InitLocals != rightBody.InitLocals ||
                leftBody.Variables.Count != rightBody.Variables.Count)
            {
                differences.Add($"Method local layout changed: {methodName}");
                continue;
            }
            for (var index = 0; index < leftBody.Variables.Count; index++)
            {
                var leftVariable = leftBody.Variables[index];
                var rightVariable = rightBody.Variables[index];
                if (leftVariable.VariableType.FullName != rightVariable.VariableType.FullName ||
                    leftVariable.IsPinned != rightVariable.IsPinned)
                {
                    differences.Add(
                        $"Method local changed: {methodName} local {index}");
                }
            }

            if (leftBody.Instructions.Count != rightBody.Instructions.Count)
            {
                differences.Add($"Instruction count changed: {methodName}");
                continue;
            }
            for (var index = 0; index < leftBody.Instructions.Count; index++)
            {
                var leftInstruction = leftBody.Instructions[index];
                var rightInstruction = rightBody.Instructions[index];
                if (leftInstruction.OpCode.Code != rightInstruction.OpCode.Code)
                {
                    differences.Add(
                        $"Opcode changed: {methodName} instruction {index} " +
                        $"{leftInstruction.OpCode} -> {rightInstruction.OpCode}");
                    continue;
                }
                if (rightInstruction.OpCode == OpCodes.Ldstr)
                {
                    localizedStringInstructionCount++;
                    if (!Equals(leftInstruction.Operand, rightInstruction.Operand))
                    {
                        changedStringInstructionCount++;
                    }
                    continue;
                }
                var leftOperand = InstructionOperandSignature(leftInstruction, left);
                var rightOperand = InstructionOperandSignature(rightInstruction, right);
                if (leftOperand != rightOperand)
                {
                    differences.Add(
                        $"Operand changed: {methodName} instruction {index} " +
                        $"{leftOperand} -> {rightOperand}");
                }
            }

            var leftHandlers = leftBody.ExceptionHandlers
                .Select(handler => ExceptionHandlerSignature(handler, left))
                .ToArray();
            var rightHandlers = rightBody.ExceptionHandlers
                .Select(handler => ExceptionHandlerSignature(handler, right))
                .ToArray();
            if (!leftHandlers.SequenceEqual(rightHandlers))
            {
                differences.Add($"Exception handlers changed: {methodName}");
            }
        }
    }

    var baselineReferences = baseline.MainModule.AssemblyReferences
        .Select(reference => reference.FullName)
        .Order()
        .ToArray();
    var localizedReferences = localized.MainModule.AssemblyReferences
        .Select(reference => reference.FullName)
        .Order()
        .ToArray();
    if (!baselineReferences.SequenceEqual(localizedReferences))
    {
        differences.Add("Assembly references changed.");
    }

    var baselineResources = baseline.MainModule.Resources
        .Select(resource => $"{resource.ResourceType}:{resource.Name}")
        .Order()
        .ToArray();
    var localizedResources = localized.MainModule.Resources
        .Select(resource => $"{resource.ResourceType}:{resource.Name}")
        .Order()
        .ToArray();
    if (!baselineResources.SequenceEqual(localizedResources))
    {
        differences.Add("Embedded resource set changed.");
    }

    return differences;
}

static void WriteAssembly(AssemblyDefinition assembly, string assemblyPath)
{
    var tempPath = assemblyPath + ".patched";
    assembly.Write(tempPath, new WriterParameters { WriteSymbols = false });
    File.Move(tempPath, assemblyPath, overwrite: true);
}

static MethodReference CreateInstanceMethodReference(
    string name,
    TypeReference returnType,
    TypeReference declaringType,
    params TypeReference[] parameterTypes)
{
    var reference = new MethodReference(name, returnType, declaringType)
    {
        HasThis = true,
    };
    foreach (var parameterType in parameterTypes)
    {
        reference.Parameters.Add(new ParameterDefinition(parameterType));
    }
    return reference;
}

static MethodDefinition EnsureFriendlyZombieHelper(
    ModuleDefinition module,
    TypeDefinition registry,
    TypeDefinition character,
    TypeDefinition zombie,
    TypeReference campType,
    MethodReference getCamp,
    FieldReference instanceField,
    FieldReference hypnosesField,
    MethodReference isInstanceValid)
{
    const string helperName = "IsFriendlyZombieForVictory";
    var existing = registry.Methods.FirstOrDefault(method => method.Name == helperName);
    if (existing is not null)
    {
        return existing;
    }

    var helper = new MethodDefinition(
        helperName,
        MethodAttributes.Assembly | MethodAttributes.Static | MethodAttributes.HideBySig,
        module.TypeSystem.Boolean);
    helper.Parameters.Add(new ParameterDefinition("character", ParameterAttributes.None, character));
    helper.Parameters.Add(new ParameterDefinition("playerCamp", ParameterAttributes.None, campType));
    helper.Body.MaxStackSize = 2;
    registry.Methods.Add(helper);

    var il = helper.Body.GetILProcessor();
    var returnTrue = il.Create(OpCodes.Ldc_I4_1);
    var returnFalse = il.Create(OpCodes.Ldc_I4_0);

    il.Append(il.Create(OpCodes.Ldarg_0));
    il.Append(il.Create(OpCodes.Isinst, zombie));
    il.Append(il.Create(OpCodes.Brfalse, returnFalse));

    // A zombie already assigned to the player's camp is always friendly.
    il.Append(il.Create(OpCodes.Ldarg_0));
    il.Append(il.Create(OpCodes.Callvirt, getCamp));
    il.Append(il.Create(OpCodes.Ldarg_1));
    il.Append(il.Create(OpCodes.Beq, returnTrue));

    // In plant-side modes, also tolerate a transient stale camp value while the
    // hypnosis state has already been applied.
    il.Append(il.Create(OpCodes.Ldarg_1));
    il.Append(il.Create(OpCodes.Brtrue, returnFalse));
    il.Append(il.Create(OpCodes.Ldarg_0));
    il.Append(il.Create(OpCodes.Ldfld, instanceField));
    il.Append(il.Create(OpCodes.Call, isInstanceValid));
    il.Append(il.Create(OpCodes.Brfalse, returnFalse));
    il.Append(il.Create(OpCodes.Ldarg_0));
    il.Append(il.Create(OpCodes.Ldfld, instanceField));
    il.Append(il.Create(OpCodes.Ldfld, hypnosesField));
    il.Append(il.Create(OpCodes.Brtrue, returnTrue));

    il.Append(returnFalse);
    il.Append(il.Create(OpCodes.Ret));
    il.Append(returnTrue);
    il.Append(il.Create(OpCodes.Ret));
    return helper;
}

static MethodDefinition EnsureWaveEnemyCounter(
    ModuleDefinition module,
    TypeDefinition wave,
    TypeDefinition manager,
    TypeDefinition character,
    TypeReference campType,
    FieldReference currentCharacterField,
    MethodReference managerGetInstance,
    MethodReference isManagerIZM2,
    MethodReference isInstanceValid,
    MethodReference getCamp,
    FieldReference instanceField,
    FieldReference hypnosesField)
{
    const string methodName = "CountActiveWaveEnemiesForVictory";
    var existing = wave.Methods.FirstOrDefault(method => method.Name == methodName);
    if (existing is not null)
    {
        return existing;
    }

    var method = new MethodDefinition(
        methodName,
        MethodAttributes.Private | MethodAttributes.HideBySig,
        module.TypeSystem.Int32);
    method.Body.InitLocals = true;
    method.Body.MaxStackSize = 3;
    wave.Methods.Add(method);

    var countLocal = new VariableDefinition(module.TypeSystem.Int32);
    var indexLocal = new VariableDefinition(module.TypeSystem.Int32);
    var campLocal = new VariableDefinition(campType);
    var characterLocal = new VariableDefinition(character);
    var managerLocal = new VariableDefinition(manager);
    method.Body.Variables.Add(countLocal);
    method.Body.Variables.Add(indexLocal);
    method.Body.Variables.Add(campLocal);
    method.Body.Variables.Add(characterLocal);
    method.Body.Variables.Add(managerLocal);

    var arrayCount = CreateInstanceMethodReference(
        "get_Count",
        module.TypeSystem.Int32,
        currentCharacterField.FieldType);
    var arrayItem = CreateInstanceMethodReference(
        "get_Item",
        character,
        currentCharacterField.FieldType,
        module.TypeSystem.Int32);

    var il = method.Body.GetILProcessor();
    var normalModeCamp = il.Create(OpCodes.Ldc_I4_1); // ZOMBIE
    var storeCamp = il.Create(OpCodes.Stloc, campLocal);
    var loopStart = il.Create(OpCodes.Ldarg_0);
    var countCharacter = il.Create(OpCodes.Ldloc, countLocal);
    var incrementIndex = il.Create(OpCodes.Ldloc, indexLocal);
    var checkLoop = il.Create(OpCodes.Ldloc, indexLocal);

    il.Append(il.Create(OpCodes.Ldc_I4_0));
    il.Append(il.Create(OpCodes.Stloc, countLocal));
    il.Append(il.Create(OpCodes.Call, managerGetInstance));
    il.Append(il.Create(OpCodes.Stloc, managerLocal));
    il.Append(il.Create(OpCodes.Ldloc, managerLocal));
    il.Append(il.Create(OpCodes.Call, isInstanceValid));
    il.Append(il.Create(OpCodes.Brfalse, normalModeCamp));
    il.Append(il.Create(OpCodes.Ldloc, managerLocal));
    il.Append(il.Create(OpCodes.Callvirt, isManagerIZM2));
    il.Append(il.Create(OpCodes.Brfalse, normalModeCamp));
    il.Append(il.Create(OpCodes.Ldc_I4_0)); // PLANT in IZM2
    il.Append(il.Create(OpCodes.Br, storeCamp));
    il.Append(normalModeCamp);
    il.Append(storeCamp);
    il.Append(il.Create(OpCodes.Ldc_I4_0));
    il.Append(il.Create(OpCodes.Stloc, indexLocal));
    il.Append(il.Create(OpCodes.Br, checkLoop));

    il.Append(loopStart);
    il.Append(il.Create(OpCodes.Ldfld, currentCharacterField));
    il.Append(il.Create(OpCodes.Ldloc, indexLocal));
    il.Append(il.Create(OpCodes.Callvirt, arrayItem));
    il.Append(il.Create(OpCodes.Stloc, characterLocal));
    il.Append(il.Create(OpCodes.Ldloc, characterLocal));
    il.Append(il.Create(OpCodes.Call, isInstanceValid));
    il.Append(il.Create(OpCodes.Brfalse, incrementIndex));
    il.Append(il.Create(OpCodes.Ldloc, characterLocal));
    il.Append(il.Create(OpCodes.Callvirt, getCamp));
    il.Append(il.Create(OpCodes.Ldloc, campLocal));
    il.Append(il.Create(OpCodes.Bne_Un, incrementIndex));

    // Hypnotized zombies are friendly even if a deferred camp update has not
    // reached the registry in this physics frame.
    il.Append(il.Create(OpCodes.Ldloc, campLocal));
    il.Append(il.Create(OpCodes.Ldc_I4_1));
    il.Append(il.Create(OpCodes.Bne_Un, countCharacter));
    il.Append(il.Create(OpCodes.Ldloc, characterLocal));
    il.Append(il.Create(OpCodes.Ldfld, instanceField));
    il.Append(il.Create(OpCodes.Call, isInstanceValid));
    il.Append(il.Create(OpCodes.Brfalse, countCharacter));
    il.Append(il.Create(OpCodes.Ldloc, characterLocal));
    il.Append(il.Create(OpCodes.Ldfld, instanceField));
    il.Append(il.Create(OpCodes.Ldfld, hypnosesField));
    il.Append(il.Create(OpCodes.Brtrue, incrementIndex));

    il.Append(countCharacter);
    il.Append(il.Create(OpCodes.Ldc_I4_1));
    il.Append(il.Create(OpCodes.Add));
    il.Append(il.Create(OpCodes.Stloc, countLocal));

    il.Append(incrementIndex);
    il.Append(il.Create(OpCodes.Ldc_I4_1));
    il.Append(il.Create(OpCodes.Add));
    il.Append(il.Create(OpCodes.Stloc, indexLocal));

    il.Append(checkLoop);
    il.Append(il.Create(OpCodes.Ldarg_0));
    il.Append(il.Create(OpCodes.Ldfld, currentCharacterField));
    il.Append(il.Create(OpCodes.Callvirt, arrayCount));
    il.Append(il.Create(OpCodes.Blt, loopStart));
    il.Append(il.Create(OpCodes.Ldloc, countLocal));
    il.Append(il.Create(OpCodes.Ret));
    return method;
}

static bool HasCall(MethodDefinition method, string methodName)
{
    return method.Body.Instructions.Any(instruction =>
        instruction.Operand is MethodReference reference &&
        reference.Name == methodName);
}

var command = args.Length > 0 ? args[0] : "";
var validArguments =
    (args.Length == 2 &&
     (command == "inspect" ||
      command == "inspect-strings" ||
      command == "patch" ||
      command == "inspect-victory" ||
      command == "patch-victory")) ||
    (args.Length == 3 &&
     (command == "patch-strings" ||
      command == "compare-logic"));
if (!validArguments)
{
    Console.Error.WriteLine(
        "Usage: PvzAssemblyPatcher <inspect|inspect-strings|patch|inspect-victory|patch-victory> <PlantsVsZombies.dll>\n" +
        "       PvzAssemblyPatcher patch-strings <PlantsVsZombies.dll> <translations.json>\n" +
        "       PvzAssemblyPatcher compare-logic <baseline.dll> <localized.dll>");
    return 2;
}

var assemblyPath = Path.GetFullPath(args[1]);
var resolver = new DefaultAssemblyResolver();
resolver.AddSearchDirectory(Path.GetDirectoryName(assemblyPath)!);
var readerParameters = new ReaderParameters
{
    InMemory = true,
    ReadSymbols = false,
    AssemblyResolver = resolver,
};

using var assembly = AssemblyDefinition.ReadAssembly(assemblyPath, readerParameters);

if (args[0] == "compare-logic")
{
    var localizedPath = Path.GetFullPath(args[2]);
    var localizedResolver = new DefaultAssemblyResolver();
    localizedResolver.AddSearchDirectory(Path.GetDirectoryName(localizedPath)!);
    var localizedReaderParameters = new ReaderParameters
    {
        InMemory = true,
        ReadSymbols = false,
        AssemblyResolver = localizedResolver,
    };
    using var localizedAssembly = AssemblyDefinition.ReadAssembly(
        localizedPath,
        localizedReaderParameters);
    var differences = CompareAssemblyLogic(
        assembly,
        localizedAssembly,
        out var localizedStringInstructionCount,
        out var changedStringInstructionCount);
    if (differences.Count > 0)
    {
        Console.Error.WriteLine(
            $"Assembly logic differs in {differences.Count} place(s):");
        foreach (var difference in differences.Take(100))
        {
            Console.Error.WriteLine($"- {difference}");
        }
        if (differences.Count > 100)
        {
            Console.Error.WriteLine(
                $"- ... {differences.Count - 100} additional difference(s)");
        }
        return 1;
    }

    Console.WriteLine(
        "Assembly logic is equivalent: " +
        $"types={EnumerateTypes(assembly.MainModule.Types).Count()} " +
        $"methods={EnumerateTypes(assembly.MainModule.Types).Sum(type => type.Methods.Count)} " +
        $"string_instructions={localizedStringInstructionCount} " +
        $"localized_strings={changedStringInstructionCount}");
    return 0;
}

if (args[0] == "patch-strings")
{
    var parsedTranslations = JsonSerializer.Deserialize<Dictionary<string, string>>(
        File.ReadAllText(Path.GetFullPath(args[2])))
        ?? throw new InvalidOperationException("Could not parse the runtime translation map.");
    var translations = parsedTranslations
        .Where(pair => ContainsCjk(pair.Key))
        .ToDictionary(pair => pair.Key, pair => pair.Value);
    if (translations.Any(pair => ContainsCjk(pair.Value)))
    {
        throw new InvalidOperationException(
            "Runtime string mappings with CJK source keys must use CJK-free values.");
    }

    var replacementCount = 0;
    var usedStrings = new HashSet<string>();
    foreach (var type in EnumerateTypes(assembly.MainModule.Types))
    {
        foreach (var method in type.Methods.Where(method => method.HasBody))
        {
            foreach (var instruction in method.Body.Instructions.Where(instruction =>
                         instruction.OpCode == OpCodes.Ldstr &&
                         instruction.Operand is string))
            {
                var source = (string)instruction.Operand;
                if (!translations.TryGetValue(source, out var translated) ||
                    translated == source)
                {
                    continue;
                }
                instruction.Operand = translated;
                replacementCount++;
                usedStrings.Add(source);
            }
        }
    }

    if (replacementCount == 0)
    {
        Console.WriteLine("No matching assembly strings required replacement.");
        return 0;
    }
    WriteAssembly(assembly, assemblyPath);
    Console.WriteLine(
        $"Patched assembly strings: instructions={replacementCount} " +
        $"source_strings={usedStrings.Count} path={assemblyPath}");
    return 0;
}

if (args[0] == "inspect-strings")
{
    var strings = EnumerateTypes(assembly.MainModule.Types)
        .SelectMany(type => type.Methods
            .Where(method => method.HasBody)
            .SelectMany(method => method.Body.Instructions
                .Where(instruction =>
                    instruction.OpCode == OpCodes.Ldstr &&
                    instruction.Operand is string value &&
                    ContainsCjk(value))
                .Select(instruction => new
                {
                    type = type.FullName,
                    method = method.FullName,
                    value = (string)instruction.Operand,
                })))
        .ToArray();
    Console.WriteLine(JsonSerializer.Serialize(
        strings,
        new JsonSerializerOptions { WriteIndented = true }));
    Console.Error.WriteLine($"CJK string instructions: {strings.Length}");
    return 0;
}

if (args[0] == "inspect-victory")
{
    var registry = assembly.MainModule.Types.Single(t => t.Name == "TowerDefenseBattleCharacterRegistry");
    var inspectedMethods = new[]
    {
        registry.Methods.Single(m => m.Name == "GetCleanCharactersList"),
        registry.Methods.Single(m => m.Name == "GetZombieCount"),
        registry.Methods.Single(m => m.Name == "TryGetFinalWaveTarget"),
        registry.Methods.Single(m => m.Name == "IsFinalWaveTargetCandidate"),
    };

    foreach (var method in inspectedMethods)
    {
        Console.WriteLine($"\nMethod: {method.FullName}");
        foreach (var instruction in method.Body.Instructions)
        {
            Console.WriteLine(instruction);
        }
    }

    var vaseProcess = assembly.MainModule.Types.Single(t => t.Name == "TowerDefenseBattleProcessVase");
    var vaseCheckFinal = vaseProcess.Methods.Single(m => m.Name == "CheckFinal");
    Console.WriteLine($"\nMethod: {vaseCheckFinal.FullName}");
    foreach (var instruction in vaseCheckFinal.Body.Instructions)
    {
        Console.WriteLine(instruction);
    }

    foreach (var targetName in new[] { "GetZombieCount", "TryGetFinalWaveTarget" })
    {
        Console.WriteLine($"\nCallers of {targetName}:");
        foreach (var type in assembly.MainModule.Types)
        {
            foreach (var method in type.Methods.Where(m => m.HasBody))
            {
                if (method.Body.Instructions.Any(instruction =>
                        instruction.Operand is MethodReference reference &&
                        reference.Name == targetName &&
                        reference.DeclaringType.Name == registry.Name))
                {
                    Console.WriteLine(method.FullName);
                }
            }
        }
    }

    return 0;
}

if (args[0] == "patch-victory")
{
    var module = assembly.MainModule;
    var registry = module.Types.Single(t => t.Name == "TowerDefenseBattleCharacterRegistry");
    var wave = module.Types.Single(t => t.Name == "TowerDefenseBattleFeatureWave");
    var vaseProcess = module.Types.Single(t => t.Name == "TowerDefenseBattleProcessVase");
    var manager = module.Types.Single(t => t.Name == "TowerDefenseManager");
    var character = module.Types.Single(t => t.Name == "TowerDefenseCharacter");
    var zombie = module.Types.Single(t => t.Name == "TowerDefenseZombie");
    var characterInstance = module.Types.Single(t => t.Name == "TowerDefenseCharacterInstance");
    var campType = module.Types
        .Single(t => t.Name == "TowerDefenseEnum")
        .NestedTypes.Single(t => t.Name == "CHARACTER_CAMP");

    var getCamp = module.ImportReference(character.Methods.Single(method =>
        method.Name == "get_camp" && method.Parameters.Count == 0));
    var instanceField = module.ImportReference(character.Fields.Single(field =>
        field.Name == "instance"));
    var hypnosesField = module.ImportReference(characterInstance.Fields.Single(field =>
        field.Name == "hypnoses"));
    var isInstanceValid = module.ImportReference(
        registry.Methods
            .Single(method => method.Name == "IsFinalWaveTargetCandidate")
            .Body.Instructions
            .Select(instruction => instruction.Operand)
            .OfType<MethodReference>()
            .First(method =>
                method.Name == "IsInstanceValid" &&
                method.DeclaringType.FullName == "Godot.GodotObject"));

    var friendlyHelper = EnsureFriendlyZombieHelper(
        module,
        registry,
        character,
        zombie,
        campType,
        getCamp,
        instanceField,
        hypnosesField,
        isInstanceValid);

    var currentCharacterField = module.ImportReference(wave.Fields.Single(field =>
        field.Name == "currentCharacter"));
    var managerGetInstance = module.ImportReference(manager.Methods.Single(method =>
        method.Name == "get_Instance" && method.Parameters.Count == 0));
    var isManagerIZM2 = module.ImportReference(manager.Methods.Single(method =>
        method.Name == "IsIZM2Mode" && method.Parameters.Count == 0));
    var waveEnemyCounter = EnsureWaveEnemyCounter(
        module,
        wave,
        manager,
        character,
        campType,
        currentCharacterField,
        managerGetInstance,
        isManagerIZM2,
        isInstanceValid,
        getCamp,
        instanceField,
        hypnosesField);

    var changes = 0;

    var wavePhysics = wave.Methods.Single(method =>
        method.Name == "WavePhysicsProcess" && method.Parameters.Count == 1);
    if (!HasCall(wavePhysics, waveEnemyCounter.Name))
    {
        var zombieCountCall = wavePhysics.Body.Instructions.Single(instruction =>
            instruction.Operand is MethodReference reference &&
            reference.Name == "GetZombieCount" &&
            reference.DeclaringType.Name == registry.Name);
        var waveIl = wavePhysics.Body.GetILProcessor();
        zombieCountCall.OpCode = OpCodes.Pop;
        zombieCountCall.Operand = null;
        var loadThis = waveIl.Create(OpCodes.Ldarg_0);
        waveIl.InsertAfter(zombieCountCall, loadThis);
        waveIl.InsertAfter(loadThis, waveIl.Create(OpCodes.Call, waveEnemyCounter));
        changes++;
        Console.WriteLine("Patched wave progression to count only active enemies for the current mode.");
    }

    var finalCandidate = registry.Methods.Single(method =>
        method.Name == "IsFinalWaveTargetCandidate");
    if (!HasCall(finalCandidate, friendlyHelper.Name))
    {
        var campGetterCall = finalCandidate.Body.Instructions.Last(instruction =>
            instruction.Operand is MethodReference reference &&
            reference.Name == "get_camp" &&
            reference.DeclaringType.Name == character.Name);
        var helperStart = campGetterCall.Previous
            ?? throw new InvalidOperationException("Could not locate the final camp comparison.");
        var finalIl = finalCandidate.Body.GetILProcessor();
        var cursor = helperStart;
        var helperInstructions = new[]
        {
            finalIl.Create(OpCodes.Ldarg_1),
            finalIl.Create(OpCodes.Call, friendlyHelper),
            finalIl.Create(OpCodes.Brfalse, finalIl.Create(OpCodes.Ldarg_0)),
            finalIl.Create(OpCodes.Ldc_I4_0),
            finalIl.Create(OpCodes.Ret),
        };
        var resumeCampCheck = (Instruction)helperInstructions[2].Operand;
        foreach (var instruction in helperInstructions)
        {
            finalIl.InsertAfter(cursor, instruction);
            cursor = instruction;
        }
        finalIl.InsertAfter(cursor, resumeCampCheck);
        changes++;
        Console.WriteLine("Patched final target selection to ignore friendly zombies.");
    }

    var tryFinalTarget = registry.Methods.Single(method =>
        method.Name == "TryGetFinalWaveTarget");
    if (!HasCall(tryFinalTarget, friendlyHelper.Name))
    {
        var pendingStore = tryFinalTarget.Body.Instructions.Single(instruction =>
            instruction.OpCode == OpCodes.Stind_I1 &&
            instruction.Previous?.OpCode == OpCodes.Ldc_I4_1);
        var pendingSetStart = pendingStore.Previous?.Previous
            ?? throw new InvalidOperationException("Could not locate the pending-destroy assignment.");
        var skipPendingSet = pendingStore.Next
            ?? throw new InvalidOperationException("Could not locate the pending-destroy continuation.");
        var zombieStore = tryFinalTarget.Body.Instructions.Single(instruction =>
            instruction.OpCode.Code.ToString().StartsWith("Stloc", StringComparison.Ordinal) &&
            instruction.Previous?.OpCode == OpCodes.Isinst &&
            instruction.Previous.Operand is TypeReference type &&
            type.Name == zombie.Name);
        var zombieLocal = zombieStore.Operand as VariableDefinition
            ?? throw new InvalidOperationException("Could not resolve the pending zombie local.");
        var pendingIl = tryFinalTarget.Body.GetILProcessor();
        foreach (var instruction in new[]
                 {
                     pendingIl.Create(OpCodes.Ldloc, zombieLocal),
                     pendingIl.Create(OpCodes.Ldarg_1),
                     pendingIl.Create(OpCodes.Call, friendlyHelper),
                     pendingIl.Create(OpCodes.Brtrue, skipPendingSet),
                 })
        {
            pendingIl.InsertBefore(pendingSetStart, instruction);
        }
        changes++;
        Console.WriteLine("Patched pending-destroy checks to ignore friendly zombies.");
    }

    var vaseCheckFinal = vaseProcess.Methods.Single(method =>
        method.Name == "CheckFinal" && method.Parameters.Count == 0);
    if (!HasCall(vaseCheckFinal, friendlyHelper.Name))
    {
        var destroyCheck = vaseCheckFinal.Body.Instructions.Single(instruction =>
            instruction.OpCode == OpCodes.Ldfld &&
            instruction.Operand is FieldReference field &&
            field.Name == "isDestroy");
        var vaseCharacterLocal = destroyCheck.Previous?.Operand as VariableDefinition
            ?? throw new InvalidOperationException("Could not resolve the vase-mode zombie local.");
        var skipDestroyCheck = vaseCheckFinal.Body.Instructions
            .SkipWhile(instruction => instruction != destroyCheck)
            .First(instruction =>
                instruction.OpCode == OpCodes.Ldfld &&
                instruction.Operand is FieldReference field &&
                field.Name == "skipDestroySet");
        var continueLoopBranch = skipDestroyCheck.Next
            ?? throw new InvalidOperationException("Could not locate the vase-mode continuation branch.");
        var continueLoop = continueLoopBranch.Operand as Instruction
            ?? throw new InvalidOperationException("Could not resolve the vase-mode continuation target.");
        var returnFalseStart = continueLoopBranch.Next
            ?? throw new InvalidOperationException("Could not locate the vase-mode false result.");
        var vaseIl = vaseCheckFinal.Body.GetILProcessor();
        foreach (var instruction in new[]
                 {
                     vaseIl.Create(OpCodes.Ldloc, vaseCharacterLocal),
                     vaseIl.Create(OpCodes.Ldc_I4_0),
                     vaseIl.Create(OpCodes.Call, friendlyHelper),
                     vaseIl.Create(OpCodes.Brtrue, continueLoop),
                 })
        {
            vaseIl.InsertBefore(returnFalseStart, instruction);
        }
        changes++;
        Console.WriteLine("Patched vase-mode cleanup checks to ignore friendly zombies.");
    }

    if (changes == 0)
    {
        Console.WriteLine("Victory logic is already patched; no changes were written.");
        return 0;
    }

    WriteAssembly(assembly, assemblyPath);
    Console.WriteLine($"\nPatched victory logic: {assemblyPath}");
    return 0;
}

var commandRegistry = assembly.MainModule.Types.Single(t => t.Name == "CommandRegistry");
var executeCommand = commandRegistry.Methods.Single(m => m.Name == "ExecuteCommand" && m.Parameters.Count == 2);

static bool IsCallableCall(Instruction instruction)
{
    return instruction.OpCode == OpCodes.Call &&
           instruction.Operand is MethodReference method &&
           method.DeclaringType.FullName == "Godot.Callable" &&
           method.Name == "Call";
}

var calls = executeCommand.Body.Instructions.Where(IsCallableCall).ToList();
Console.WriteLine($"Method: {executeCommand.FullName}");
Console.WriteLine($"Callable.Call count: {calls.Count}");
foreach (var call in calls)
{
    var index = executeCommand.Body.Instructions.IndexOf(call);
    Console.WriteLine($"\nCallable.Call at IL_{call.Offset:x4}:");
    for (var i = Math.Max(0, index - 12); i <= Math.Min(executeCommand.Body.Instructions.Count - 1, index + 3); i++)
    {
        Console.WriteLine(executeCommand.Body.Instructions[i]);
    }
}

if (args[0] == "inspect")
{
    return 0;
}

// The final call invokes the registered command callback. The original game wraps the
// entire Godot Array inside one Variant instead of spreading its elements as Callable
// arguments. Rebuild a Variant[] from every converted element so zero-, one-, and
// multi-argument commands all receive the arity and values they declared.
var callbackCall = calls.Last();
var callbackCallIndex = executeCommand.Body.Instructions.IndexOf(callbackCall);
var implicitConversion = executeCommand.Body.Instructions
    .Take(callbackCallIndex)
    .Reverse()
    .FirstOrDefault(instruction =>
        instruction.OpCode == OpCodes.Call &&
        instruction.Operand is MethodReference method &&
        method.Name == "op_Implicit" &&
        method.ReturnType.FullName == "Godot.Variant" &&
        method.Parameters.Count == 1 &&
        method.Parameters[0].ParameterType.FullName == "Godot.Collections.Array");

if (implicitConversion is null)
{
    Console.WriteLine("The command callback no longer contains the wrapped Array conversion; no patch was applied.");
    return 0;
}

var implicitMethod = (MethodReference)implicitConversion.Operand;
var arrayType = implicitMethod.Parameters[0].ParameterType.Resolve();
var countGetter = assembly.MainModule.ImportReference(arrayType.Methods.Single(method =>
    method.Name == "get_Count" &&
    method.Parameters.Count == 0 &&
    method.ReturnType.MetadataType == MetadataType.Int32));
var itemGetter = assembly.MainModule.ImportReference(arrayType.Methods.Single(method =>
    method.Name == "get_Item" &&
    method.Parameters.Count == 1 &&
    method.Parameters[0].ParameterType.MetadataType == MetadataType.Int32 &&
    method.ReturnType.FullName == "Godot.Variant"));

var callbackFieldInstruction = executeCommand.Body.Instructions
    .Take(callbackCallIndex)
    .Reverse()
    .First(instruction =>
        instruction.OpCode == OpCodes.Ldflda &&
        instruction.Operand is FieldReference field &&
        field.Name == "Callback" &&
        field.FieldType.FullName == "Godot.Callable");
var callbackField = (FieldReference)callbackFieldInstruction.Operand;
var tailStart = callbackFieldInstruction.Previous
    ?? throw new InvalidOperationException("Could not find the start of the command callback tail.");
var commandConfigLocal = tailStart.Operand as VariableDefinition
    ?? throw new InvalidOperationException("Could not resolve the CommandConfig local.");
var convertedArgsLocal = executeCommand.Body.Variables.Single(variable =>
    variable.VariableType.FullName == "Godot.Collections.Array");
var callableCall = (MethodReference)callbackCall.Operand;
var variantArrayType = callableCall.Parameters[0].ParameterType;
var variantType = ((ArrayType)variantArrayType).ElementType;
var spreadArgsLocal = new VariableDefinition(variantArrayType);
var indexLocal = new VariableDefinition(assembly.MainModule.TypeSystem.Int32);
executeCommand.Body.Variables.Add(spreadArgsLocal);
executeCommand.Body.Variables.Add(indexLocal);
executeCommand.Body.InitLocals = true;

var il = executeCommand.Body.GetILProcessor();
while (tailStart.Next is not null)
{
    il.Remove(tailStart.Next);
}

tailStart.OpCode = OpCodes.Ldloc;
tailStart.Operand = convertedArgsLocal;

var loopStart = il.Create(OpCodes.Ldloc, spreadArgsLocal);
var checkStart = il.Create(OpCodes.Ldloc, indexLocal);
var instructions = new[]
{
    il.Create(OpCodes.Callvirt, countGetter),
    il.Create(OpCodes.Newarr, variantType),
    il.Create(OpCodes.Stloc, spreadArgsLocal),
    il.Create(OpCodes.Ldc_I4_0),
    il.Create(OpCodes.Stloc, indexLocal),
    il.Create(OpCodes.Br, checkStart),
    loopStart,
    il.Create(OpCodes.Ldloc, indexLocal),
    il.Create(OpCodes.Ldloc, convertedArgsLocal),
    il.Create(OpCodes.Ldloc, indexLocal),
    il.Create(OpCodes.Callvirt, itemGetter),
    il.Create(OpCodes.Stelem_Any, variantType),
    il.Create(OpCodes.Ldloc, indexLocal),
    il.Create(OpCodes.Ldc_I4_1),
    il.Create(OpCodes.Add),
    il.Create(OpCodes.Stloc, indexLocal),
    checkStart,
    il.Create(OpCodes.Ldloc, convertedArgsLocal),
    il.Create(OpCodes.Callvirt, countGetter),
    il.Create(OpCodes.Blt, loopStart),
    il.Create(OpCodes.Ldloc, commandConfigLocal),
    il.Create(OpCodes.Ldflda, callbackField),
    il.Create(OpCodes.Ldloc, spreadArgsLocal),
    il.Create(OpCodes.Call, callableCall),
    il.Create(OpCodes.Pop),
    il.Create(OpCodes.Ret),
};

foreach (var instruction in instructions)
{
    il.Append(instruction);
}

var tempPath = assemblyPath + ".patched";
assembly.Write(tempPath, new WriterParameters { WriteSymbols = false });
File.Move(tempPath, assemblyPath, overwrite: true);
Console.WriteLine($"\nPatched: {assemblyPath}");
return 0;

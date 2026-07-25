using Mono.Cecil;
using Mono.Cecil.Cil;

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

if (args.Length != 2 ||
    (args[0] != "inspect" &&
     args[0] != "patch" &&
     args[0] != "inspect-victory" &&
     args[0] != "patch-victory"))
{
    Console.Error.WriteLine("Usage: PvzAssemblyPatcher <inspect|patch|inspect-victory|patch-victory> <PlantsVsZombies.dll>");
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

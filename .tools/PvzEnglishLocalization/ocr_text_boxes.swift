#!/usr/bin/env swift
// Locate Chinese text regions in a graphic catalog or every PNG below a root.

import Foundation
import ImageIO
import Vision

guard CommandLine.arguments.count == 4 || CommandLine.arguments.count == 5
else {
    fputs(
        "usage: ocr_text_boxes.swift GUI_ROOT CATALOG_JSON OUTPUT_JSON\n"
            + "       ocr_text_boxes.swift GUI_ROOT --all OUTPUT_JSON\n"
            + "       ocr_text_boxes.swift GUI_ROOT --all-text OUTPUT_JSON\n"
            + "       ocr_text_boxes.swift GUI_ROOT BATCH_JSON OUTPUT_JSON"
            + " --all-text\n",
        stderr
    )
    exit(2)
}

let root = URL(
    fileURLWithPath: CommandLine.arguments[1],
    isDirectory: true
)
let outputURL = URL(fileURLWithPath: CommandLine.arguments[3])
let selection = CommandLine.arguments[2]
let relativePaths: [String]
let includeAllText = selection == "--all-text"
    || (
        CommandLine.arguments.count == 5
            && CommandLine.arguments[4] == "--all-text"
    )
if selection == "--all" || selection == "--all-text" {
    guard
        let enumerator = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        )
    else {
        fatalError("Cannot enumerate \(root.path)")
    }
    var discovered: [String] = []
    for case let file as URL in enumerator {
        guard file.pathExtension.lowercased() == "png" else {
            continue
        }
        let prefixLength = root.path.count + 1
        discovered.append(String(file.path.dropFirst(prefixLength)))
    }
    relativePaths = discovered.sorted()
} else {
    let catalogURL = URL(fileURLWithPath: selection)
    let catalogData = try Data(contentsOf: catalogURL)
    guard let catalog = try JSONSerialization.jsonObject(
        with: catalogData
    ) as? [String: Any]
    else {
        fatalError("Graphic-text catalog must be a JSON object")
    }
    if let records = catalog["records"] as? [[String: Any]] {
        relativePaths = records.compactMap { $0["path"] as? String }.sorted()
    } else {
        relativePaths = catalog.keys.sorted()
    }
}

func containsCJK(_ text: String) -> Bool {
    text.unicodeScalars.contains { scalar in
        (0x3400...0x4DBF).contains(scalar.value)
            || (0x4E00...0x9FFF).contains(scalar.value)
    }
}

var output: [[String: Any]] = []
for relative in relativePaths {
    let file = root.appendingPathComponent(relative)
    guard
        let source = CGImageSourceCreateWithURL(file as CFURL, nil),
        let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
    else {
        fatalError("Cannot load \(file.path)")
    }
    if image.width <= 2 || image.height <= 2 {
        output.append(
            [
                "path": relative,
                "width": image.width,
                "height": image.height,
                "boxes": [],
            ]
        )
        continue
    }

    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = false
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    try handler.perform([request])

    var boxes: [[String: Any]] = []
    for observation in request.results ?? [] {
        guard
            let candidate = observation.topCandidates(1).first,
            includeAllText || containsCJK(candidate.string)
        else {
            continue
        }
        let box = observation.boundingBox
        let x = Int(floor(box.minX * Double(image.width)))
        let y = Int(
            floor((1.0 - box.maxY) * Double(image.height))
        )
        let maxX = Int(ceil(box.maxX * Double(image.width)))
        let maxY = Int(
            ceil((1.0 - box.minY) * Double(image.height))
        )
        boxes.append(
            [
                "text": candidate.string,
                "box": [x, y, maxX - x, maxY - y],
            ]
        )
    }
    output.append(
        [
            "path": relative,
            "width": image.width,
            "height": image.height,
            "boxes": boxes,
        ]
    )
}

let encoded = try JSONSerialization.data(
    withJSONObject: [
        "records": output,
        "record_count": output.count,
    ],
    options: [.prettyPrinted, .sortedKeys]
)
try encoded.write(to: outputURL, options: .atomic)
print("Wrote OCR boxes for \(output.count) localized graphic textures")

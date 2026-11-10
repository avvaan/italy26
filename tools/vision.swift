// Локальный анализ кадров через Apple Vision: лица, люди, тема кадра.
// Ничего не отправляет в сеть. Вход — пути к уменьшенным JPEG (по одному в строке на stdin),
// выход — JSON-строка на каждый файл: {"path", "faces", "big_face", "humans", "labels"}.
//   swiftc -O tools/vision.swift -o .cache/vision && ls *.jpg | .cache/vision
import Foundation
import Vision

func analyze(_ path: String) -> [String: Any] {
    let url = URL(fileURLWithPath: path)
    let handler = VNImageRequestHandler(url: url, options: [:])
    let faces = VNDetectFaceRectanglesRequest()
    let humans = VNDetectHumanRectanglesRequest()
    let classify = VNClassifyImageRequest()
    var out: [String: Any] = ["path": path]
    do {
        try handler.perform([faces, humans, classify])
        let f = faces.results ?? []
        out["faces"] = f.count
        // крупный план: лицо занимает больше 4% кадра
        out["big_face"] = f.contains { $0.boundingBox.width * $0.boundingBox.height > 0.04 }
        out["humans"] = (humans.results ?? []).filter { $0.confidence > 0.5 }.count
        let labels = (classify.results ?? []).filter { $0.confidence > 0.3 }.prefix(8).map { $0.identifier }
        out["labels"] = Array(labels)
    } catch {
        out["error"] = error.localizedDescription
    }
    return out
}

while let line = readLine() {
    let p = line.trimmingCharacters(in: .whitespaces)
    if p.isEmpty { continue }
    if let data = try? JSONSerialization.data(withJSONObject: analyze(p)),
       let s = String(data: data, encoding: .utf8) {
        print(s)
        fflush(stdout)
    }
}

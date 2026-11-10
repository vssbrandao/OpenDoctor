// Exporta SF Symbols (Medium) como SVG vetorial, no formato dos web/assets/icons/sf-*.svg (preenchimento #8B8B8B).
// O nome do símbolo não leva ao glifo da fonte: desenha o NSImage(systemSymbolName:) e procura, entre os glifos da área
// privada (U+100000…) do SFSymbolsFallback.otf, o de desenho mais parecido; exporta o "uniXXXXXX.medium" dele.
// Uso:  xcrun swiftc -O scripts/sf_symbols.swift -o /tmp/sf_symbols && [SF_PESO=semibold] /tmp/sf_symbols <pasta> <tamanho> nome[=arquivo] ...
// (sem SF_PESO: o Regular da fonte reserva, escala Medium — os sf-*.svg do Criar evento; SF_PESO=Ultralight, Thin, Light,
// Regular, Medium, Semibold, Bold, Heavy ou Black: o símbolo da SF Pro Display daquele peso, instalada em /Library/Fonts)
// (só roda no Mac com o app SF Symbols; a licença da Apple limita o uso dos símbolos — ver a memória do projeto)
import AppKit
import CoreText

let FONTE = "/Applications/SF Symbols.app/Contents/Resources/Fonts/SFSymbolsFallback.otf"
let N = 32   // a comparação é feita em 32×32, com o desenho esticado na própria caixa

func mascara(_ desenha: (CGContext) -> Void, _ w: Int, _ h: Int) -> [UInt8] {
    var px = [UInt8](repeating: 0, count: w * h)
    let ctx = CGContext(data: &px, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w,
                        space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGImageAlphaInfo.none.rawValue)!
    ctx.setFillColor(gray: 0, alpha: 1); ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.setFillColor(gray: 1, alpha: 1)
    desenha(ctx)
    return px
}

func normaliza(_ px: [UInt8], _ w: Int, _ h: Int) -> ([Float], Float)? {
    var x0 = w, y0 = h, x1 = -1, y1 = -1
    for y in 0..<h { for x in 0..<w where px[y * w + x] > 96 { x0 = min(x0, x); x1 = max(x1, x); y0 = min(y0, y); y1 = max(y1, y) } }
    if x1 < 0 { return nil }
    let bw = Float(x1 - x0 + 1), bh = Float(y1 - y0 + 1)
    var out = [Float](repeating: 0, count: N * N)
    for j in 0..<N { for i in 0..<N {
        let sx = x0 + Int(Float(i) / Float(N) * bw), sy = y0 + Int(Float(j) / Float(N) * bh)
        out[j * N + i] = Float(px[min(sy, h - 1) * w + min(sx, w - 1)]) / 255
    } }
    return (out, bw / bh)
}

let prov = CGDataProvider(url: URL(fileURLWithPath: FONTE) as CFURL)!
let cg = CGFont(prov)!
let ct = CTFontCreateWithGraphicsFont(cg, 200, nil, nil)
let cs = CTFontCopyCharacterSet(ct) as CharacterSet

// os glifos da área privada, já normalizados
var glifos: [(UInt32, CGGlyph, [Float], Float)] = []
for cp in UInt32(0x100000)...UInt32(0x10FFFD) {
    guard let u = Unicode.Scalar(cp), cs.contains(u) else { continue }
    var utf16 = Array(String(Character(u)).utf16), g = [CGGlyph](repeating: 0, count: 2)
    guard CTFontGetGlyphsForCharacters(ct, &utf16, &g, utf16.count), g[0] != 0, let path = CTFontCreatePathForGlyph(ct, g[0], nil) else { continue }
    let b = path.boundingBoxOfPath
    if b.width < 1 || b.height < 1 { continue }
    let px = mascara({ ctx in ctx.translateBy(x: -b.minX + 4, y: -b.minY + 4); ctx.addPath(path); ctx.fillPath() }, Int(b.width) + 8, Int(b.height) + 8)
    if let (v, r) = normaliza(px, Int(b.width) + 8, Int(b.height) + 8) { glifos.append((cp, g[0], v, r)) }
}

let args = CommandLine.arguments
let pasta = args[1], tam = CGFloat(Double(args[2])!)
let ctTam = CTFontCreateWithGraphicsFont(cg, tam, nil, nil)
for pedido in args.dropFirst(3) {
    let partes = pedido.split(separator: "=").map(String.init)
    let nome = partes[0], arquivo = partes.count > 1 ? partes[1] : "sf-" + nome.replacingOccurrences(of: ".", with: "-")
    let cfg = NSImage.SymbolConfiguration(pointSize: 160, weight: .medium)
    guard let img = NSImage(systemSymbolName: nome, accessibilityDescription: nil)?.withSymbolConfiguration(cfg),
          let cgimg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { print("sem símbolo:", nome); continue }
    let w = cgimg.width, h = cgimg.height
    let px = mascara({ ctx in ctx.clip(to: CGRect(x: 0, y: 0, width: w, height: h), mask: cgimg); ctx.fill(CGRect(x: 0, y: 0, width: w, height: h)) }, w, h)
    guard let (alvo, ra) = normaliza(px, w, h) else { print("vazio:", nome); continue }
    var melhor: (UInt32, Float) = (0, .infinity)
    for (cp, _, v, r) in glifos {
        var d: Float = 0
        for k in 0..<(N * N) { let e = v[k] - alvo[k]; d += e * e }
        d += abs(log(r / ra)) * 200
        if d < melhor.1 { melhor = (cp, d) }
    }
    // o peso: a fonte reserva só tem o Regular (o ".medium" do nome é a escala Medium); com SF_PESO o glifo vem da
    // SF Pro Display daquele peso (/Library/Fonts/SF-Pro-Display-<Peso>.otf), que traz os símbolos nos mesmos códigos
    let path: CGPath
    if let peso = ProcessInfo.processInfo.environment["SF_PESO"] {
        let f = "/Library/Fonts/SF-Pro-Display-" + peso + ".otf"
        guard let pv = CGDataProvider(url: URL(fileURLWithPath: f) as CFURL), let cgp = CGFont(pv) else { print("sem fonte:", f); continue }
        let ctp = CTFontCreateWithGraphicsFont(cgp, tam, nil, nil)
        var u16 = Array(String(Character(Unicode.Scalar(melhor.0)!)).utf16), gg = [CGGlyph](repeating: 0, count: 2)
        guard CTFontGetGlyphsForCharacters(ctp, &u16, &gg, u16.count), gg[0] != 0, let pp = CTFontCreatePathForGlyph(ctp, gg[0], nil) else { print("sem símbolo em", f); continue }
        path = pp
    } else {
        let gnome = String(format: "uni%06X.medium", melhor.0)
        let g = cg.getGlyphWithGlyphName(name: gnome as CFString)
        guard g != 0, let pp = CTFontCreatePathForGlyph(ctTam, g, nil) else { print("sem glifo:", gnome); continue }
        path = pp
    }
    let b = path.boundingBoxOfPath
    var d = ""
    func p(_ q: CGPoint) -> String { String(format: "%.3f %.3f", q.x - b.minX, b.maxY - q.y) }
    path.applyWithBlock { el in
        let e = el.pointee, pt = e.points
        switch e.type {
        case .moveToPoint: d += "M" + p(pt[0])
        case .addLineToPoint: d += "L" + p(pt[0])
        case .addQuadCurveToPoint: d += "Q" + p(pt[0]) + " " + p(pt[1])
        case .addCurveToPoint: d += "C" + p(pt[0]) + " " + p(pt[1]) + " " + p(pt[2])
        case .closeSubpath: d += "Z"
        @unknown default: break
        }
    }
    func num(_ v: CGFloat) -> String {   // 14.60 -> 14.6, 13.00 -> 13; arredonda para cima (14.941 -> 14.95), senão a beirada sai cortada
        var t = String(format: "%.2f", (v * 100).rounded(.up) / 100)
        while t.hasSuffix("0") { t.removeLast() }
        if t.hasSuffix(".") { t.removeLast() }
        return t
    }
    let W = num(b.width), H = num(b.height)
    let svg = "<svg width=\"\(W)\" height=\"\(H)\" viewBox=\"0 0 \(W) \(H)\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"\(d)\" fill=\"#8B8B8B\"/></svg>\n"
    try! svg.write(toFile: pasta + "/" + arquivo + ".svg", atomically: true, encoding: .utf8)
    print(nome, String(format: "U+%06X", melhor.0), "dist", Int(melhor.1), W, "x", H, "->", arquivo + ".svg")
}

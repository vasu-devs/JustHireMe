import SwiftUI

enum Theme {
    static let accent = Color(red: 0.73, green: 0.25, blue: 0.10)
    static let ink = Color.primary
    static let background = Color(uiColor: .systemGroupedBackground)
    static let card = Color(uiColor: .secondarySystemGroupedBackground)
}

struct Eyebrow: View {
    let text: String
    var body: some View {
        Text(text.uppercased()).font(.caption.weight(.bold)).tracking(2).foregroundStyle(.secondary)
    }
}

struct ActionButton: View {
    let title: String
    var busy = false
    var action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack {
                if busy { ProgressView().tint(.white) }
                Text(title).fontWeight(.semibold)
            }.frame(maxWidth: .infinity).padding(.vertical, 10)
        }
        .buttonStyle(.borderedProminent).buttonBorderShape(.roundedRectangle(radius: 16))
        .disabled(busy)
    }
}

struct InlineMessage: View {
    let text: String
    var body: some View {
        Label(text, systemImage: "info.circle")
            .font(.callout).foregroundStyle(.secondary).padding()
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.card, in: RoundedRectangle(cornerRadius: 16))
    }
}

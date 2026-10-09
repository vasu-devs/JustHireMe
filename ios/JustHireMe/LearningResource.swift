import Foundation

struct LearningResource {
    var title: String
    var url: URL
    var exercise: String
    static func forSkill(_ skill: String) -> Self {
        let entries: [String: (String, String, String)] = [
            "Swift": ("The Swift programming language", "https://docs.swift.org/swift-book/documentation/the-swift-programming-language/", "Model an asynchronous request with loading, success and failure states."),
            "RAG": ("Retrieval with PostgreSQL", "https://www.postgresql.org/docs/current/textsearch.html", "Build a small retrieval benchmark and measure whether the relevant source appears in the results."),
            "Python": ("Python tutorial", "https://docs.python.org/3/tutorial/", "Write a small script that reads a file, validates its input and reports errors."),
            "FastAPI": ("FastAPI tutorial", "https://fastapi.tiangolo.com/tutorial/", "Build one typed endpoint with validation and a test for its error response."),
            "TypeScript": ("TypeScript handbook", "https://www.typescriptlang.org/docs/handbook/intro.html", "Model an API response with explicit types and handle each possible state."),
            "JavaScript": ("MDN JavaScript guide", "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide", "Build one small interaction and explain how it works in your portfolio."),
            "React": ("React documentation", "https://react.dev/learn", "Build a form with loading, success and error states."),
            "Kubernetes": ("Kubernetes basics", "https://kubernetes.io/docs/tutorials/kubernetes-basics/", "Deploy a small service, inspect its logs and practise rolling back a change."),
            "Docker": ("Docker getting started", "https://docs.docker.com/get-started/", "Containerize a small API with a health check and documented configuration."),
            "PostgreSQL": ("PostgreSQL tutorial", "https://www.postgresql.org/docs/current/tutorial.html", "Write a transaction and test what happens when two requests update the same row."),
            "SQL": ("PostgreSQL tutorial", "https://www.postgresql.org/docs/current/tutorial.html", "Write a query with a join, inspect its query plan and explain the index you chose."),
            "GraphQL": ("GraphQL introduction", "https://graphql.org/learn/", "Define a small schema and query just the fields a client needs.")
        ]
        let entry = entries[skill] ?? ("W3C accessibility tutorials", "https://www.w3.org/WAI/tutorials/", "Build one accessible component. Document its states and keyboard behavior.")
        return Self(title: entry.0, url: URL(string: entry.1)!, exercise: entry.2)
    }
}

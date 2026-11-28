val kotlinVersion = "2.1.10"
val ktorVersion = "3.1.2"

plugins {
    kotlin("jvm") version "2.1.10"
    kotlin("plugin.serialization") version "2.1.10"
    application
}

repositories { mavenCentral() }

dependencies {
    // Kotlin / coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.10.1")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.8.1")

    // Ktor server + client
    implementation("io.ktor:ktor-server-core-jvm:$ktorVersion")
    implementation("io.ktor:ktor-server-netty-jvm:$ktorVersion")
    implementation("io.ktor:ktor-server-content-negotiation-jvm:$ktorVersion")
    implementation("io.ktor:ktor-serialization-kotlinx-json-jvm:$ktorVersion")
    implementation("io.ktor:ktor-server-websockets-jvm:$ktorVersion")
    implementation("io.ktor:ktor-client-core-jvm:$ktorVersion")
    implementation("io.ktor:ktor-client-okhttp-jvm:$ktorVersion")
    implementation("io.ktor:ktor-client-content-negotiation-jvm:$ktorVersion")
    implementation("ch.qos.logback:logback-classic:1.5.16")

    // Adapters: H3, Redis, SQLite (local stand-in for MS SQL), Kafka
    implementation("com.uber:h3:4.3.1")
    implementation("io.lettuce:lettuce-core:6.5.0.RELEASE")
    implementation("org.xerial:sqlite-jdbc:3.49.1.0")
    implementation("org.apache.kafka:kafka-clients:3.9.0")

    // Tests (in-memory, no external services)
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testImplementation("io.mockk:mockk:1.13.17")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.1")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

kotlin { jvmToolchain(21) }

tasks.test { useJUnitPlatform() }

application { mainClass.set("com.instantmechanic.dispatch.ApplicationKt") }

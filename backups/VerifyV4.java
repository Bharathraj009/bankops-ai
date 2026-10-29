import org.flywaydb.core.Flyway;

class VerifyV4 {
    public static void main(String[] args) {
        var flyway = Flyway.configure()
            .dataSource(System.getenv("VERIFY_DB_URL"), System.getenv("VERIFY_DB_USER"), System.getenv("VERIFY_DB_PASSWORD"))
            .locations("filesystem:backend/banking-service/src/main/resources/db/migration")
            .defaultSchema("public").target("4").ignoreMigrationPatterns("*:pending").load();
        flyway.validate();
        flyway.migrate();
        // After migration, validate with no pending-migration exemption.
        var verification = Flyway.configure()
            .dataSource(System.getenv("VERIFY_DB_URL"), System.getenv("VERIFY_DB_USER"), System.getenv("VERIFY_DB_PASSWORD"))
            .locations("filesystem:backend/banking-service/src/main/resources/db/migration")
            .defaultSchema("public").target("4").load();
        verification.validate();
        var version = verification.info().current();
        if (version == null || !"4".equals(version.getVersion().toString())) {
            throw new IllegalStateException("Flyway version is not V4");
        }
        System.out.println("Verified Flyway V4 and V1-V4 checksums");
    }
}

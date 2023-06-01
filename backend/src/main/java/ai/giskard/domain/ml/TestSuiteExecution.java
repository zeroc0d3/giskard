package ai.giskard.domain.ml;

import ai.giskard.domain.BaseEntity;
import ai.giskard.utils.JSONStringAttributeConverter;
import ai.giskard.web.dto.ml.SingleTestResultDTO;
import com.fasterxml.jackson.core.type.TypeReference;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import javax.persistence.*;
import java.util.Date;
import java.util.Map;

@Entity
@NoArgsConstructor
@Getter
@Setter
public class TestSuiteExecution extends BaseEntity {

    @Converter
    public static class SingleTestResultConverter extends JSONStringAttributeConverter<Map<String, SingleTestResultDTO>> {
        @Override
        public TypeReference<Map<String, SingleTestResultDTO>> getValueTypeRef() {
            return new TypeReference<>() {
            };
        }
    }

    @ManyToOne
    TestSuiteNew suite;
    Date executionDate = new Date();
    @Enumerated(EnumType.STRING)
    TestResult result;

    @Column(columnDefinition = "VARCHAR")
    @Convert(converter = SingleTestResultConverter.class)
    private Map<String, SingleTestResultDTO> results;

    public TestSuiteExecution(TestSuiteNew suite) {
        this.suite = suite;
    }
}
